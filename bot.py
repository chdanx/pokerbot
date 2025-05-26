from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from database import init_db, get_session, PokerGame
from datetime import datetime
import logging
from collections import defaultdict

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
engine = init_db()
session = get_session(engine)

CITIES = ['Санкт-Петербург', 'Архангельск', 'Выборг']
PLAYERS = ['Данила Бадецкий', 'Данил 72 Сергеев', 'Семен Попович', 
            'Слава Харьков', 'Дмитрий Бедарев', 'Дмитрий Ляпин', 'Максим Мерзлый',
            'Максим Гомозов', 'Богдан Светоносов', 'Евгений Черницкий', 'Роман Р']

# Состояния бота
(
    MAIN_MENU,
    ADD_DATE,
    ADD_CITY,
    ADD_PLAYERS_COUNT,
    ADD_WINNER,
    ADD_SECOND_PLACE,
    ADD_REBUYS,
    ADD_BUYIN,
    ADD_BIG_BLIND,
    ADD_DESCRIPTION,
    SEARCH_GAME,
    PLAYER_STATS,
    DELETE_GAME,
    DELETE_GAME_SELECT,
    PLAYER_STATS
) = range(15)

# Создаем клавиатуры
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        ['Добавить игру', 'Последние игры'],
        ['Статистика игроков', 'Найти игру'],
        ['Удалить игру']
    ], resize_keyboard=True)

def get_cities_keyboard():
    return ReplyKeyboardMarkup([[city] for city in CITIES] + [['Отмена']], resize_keyboard=True)

def get_players_keyboard():
    return ReplyKeyboardMarkup([[player] for player in PLAYERS] + [['Отмена']], resize_keyboard=True)

async def delete_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if 'delete_options' in context.user_data:
            del context.user_data['delete_options']
            
        await update.message.reply_text(
            "✏️ Введите дату игры для удаления (ДД.ММ.ГГГГ) или нажмите 'Список':",
            reply_markup=ReplyKeyboardMarkup(
                [['Список', 'Отмена']],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        return DELETE_GAME
    except Exception as e:
        logger.error(f"Error in delete_game_start: {e}")
        await update.message.reply_text("Ошибка при запуске удаления")
        return MAIN_MENU

async def delete_game_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        text = update.message.text.strip()
        
        if text == 'Отмена':
            return await cancel(update, context)
            
        if text == 'Список':
            games = session.query(PokerGame).order_by(PokerGame.date.desc()).limit(5).all()
            if not games:
                await update.message.reply_text("Нет последних игр для удаления")
                return MAIN_MENU
                
            keyboard = []
            context.user_data['delete_options'] = {}
            
            response = "Выберите игру для удаления:\n\n"
            for i, game in enumerate(games, 1):
                response += f"{i}. {game.date.strftime('%d.%m.%Y')} - {game.winner}\n"
                keyboard.append([str(i)])
                context.user_data['delete_options'][str(i)] = game.id
                
            keyboard.append(['Отмена'])
            
            await update.message.reply_text(
                response,
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return DELETE_GAME_SELECT
            
        # Обработка ввода даты
        try:
            date_obj = datetime.strptime(text, '%d.%m.%Y').date()
            games = session.query(PokerGame).filter(PokerGame.date == date_obj).all()
            
            if not games:
                await update.message.reply_text("Игр на эту дату не найдено")
                return DELETE_GAME
                
            if len(games) == 1:
                game = games[0]
                session.delete(game)
                session.commit()
                await update.message.reply_text(
                    f"✅ Игра удалена:\n{game.date.strftime('%d.%m.%Y')}",
                    reply_markup=get_main_keyboard()
                )
                return MAIN_MENU
            else:
                context.user_data['delete_options'] = {
                    str(i): game.id for i, game in enumerate(games, 1)
                }
                response = "Найдено несколько игр:\n\n"
                for i, game in enumerate(games, 1):
                    response += f"{i}. {game.winner} (Банк: {game.bank})\n"
                    
                await update.message.reply_text(
                    response,
                    reply_markup=ReplyKeyboardMarkup(
                        [[str(i)] for i in range(1, len(games)+1)] + [['Отмена']],
                        resize_keyboard=True
                    )
                )
                return DELETE_GAME_SELECT
                
        except ValueError:
            await update.message.reply_text("Неверный формат даты. Используйте ДД.ММ.ГГГГ")
            return DELETE_GAME
            
    except Exception as e:
        logger.error(f"Error in delete_game_execute: {e}")
        await update.message.reply_text("Ошибка при обработке удаления")
        return MAIN_MENU

async def delete_game_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message.text == 'Отмена':
            return await cancel(update, context)
            
        if 'delete_options' not in context.user_data:
            await update.message.reply_text("Сессия устарела, начните заново")
            return MAIN_MENU
            
        choice = update.message.text.strip()
        if choice not in context.user_data['delete_options']:
            await update.message.reply_text("Выберите номер из списка")
            return DELETE_GAME_SELECT
            
        game_id = context.user_data['delete_options'][choice]
        game = session.query(PokerGame).get(game_id)
        
        if not game:
            await update.message.reply_text("Игра не найдена")
            return MAIN_MENU
            
        session.delete(game)
        session.commit()
        
        await update.message.reply_text(
            f"✅ Игра успешно удалена:\n"
            f"Дата: {game.date.strftime('%d.%m.%Y')}\n"
            f"Победитель: {game.winner}",
            reply_markup=get_main_keyboard()
        )
        return MAIN_MENU
        
    except Exception as e:
        logger.error(f"Error in delete_game_select: {e}")
        await update.message.reply_text("Ошибка при удалении")
        return MAIN_MENU

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    with open('hi_pic.jpg', 'rb') as photo:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=InputFile(photo),
            caption="Привет, мои техаско-канзаские друзья! Я создал этого бота на замену гугл таблице, надеюсь вам хоть чуть-чуть будет в прикол добавлять записи, но а если нет, то похуй, это был мой первый опыт создания бота! Пишите насчет предложений и багов! Позже допилю. Это начало чего-то большего!!\nВыберите действие:",
            reply_markup=get_main_keyboard()
        )
    return MAIN_MENU
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Действие отменено. Выберите новое действие:",
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

async def add_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Очищаем предыдущие данные
    context.user_data.clear()
    await update.message.reply_text(
        "Введите дату игры (ДД.ММ.ГГГГ):",
        reply_markup=ReplyKeyboardMarkup([['Отмена']], resize_keyboard=True)
    )
    return ADD_DATE

async def add_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        date_obj = datetime.strptime(update.message.text, '%d.%m.%Y').date()
        context.user_data['game_date'] = date_obj
        await update.message.reply_text(
            "Выберите город:",
            reply_markup=get_cities_keyboard()
        )
        return ADD_CITY
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Попробуйте еще раз (ДД.ММ.ГГГГ):")
        return ADD_DATE

async def add_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text not in CITIES:
        await update.message.reply_text("Пожалуйста, выберите город из списка:")
        return ADD_CITY
    
    context.user_data['city'] = update.message.text
    await update.message.reply_text(
        "Введите количество игроков:",
        reply_markup=ReplyKeyboardRemove()  
    )
    return ADD_PLAYERS_COUNT

async def add_players_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        players_count = int(update.message.text)
        if players_count < 2:
            await update.message.reply_text("Должно быть минимум 2 игрока. Введите число:")
            return ADD_PLAYERS_COUNT
            
        context.user_data['players_count'] = players_count
        await update.message.reply_text(
            "Выберите победителя:",
            reply_markup=get_players_keyboard()
        )
        return ADD_WINNER
    except ValueError:
        await update.message.reply_text("Введите число:")
        return ADD_PLAYERS_COUNT

async def add_winner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text not in PLAYERS:
        await update.message.reply_text("Пожалуйста, выберите игрока из списка:")
        return ADD_WINNER
    
    context.user_data['winner'] = update.message.text
    await update.message.reply_text(
        "Выберите занявшего 2 место:",
        reply_markup=get_players_keyboard()
    )
    return ADD_SECOND_PLACE

async def add_second_place(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text not in PLAYERS:
        await update.message.reply_text("Пожалуйста, выберите игрока из списка:")
        return ADD_SECOND_PLACE
    
    context.user_data['second_place'] = update.message.text
    await update.message.reply_text(
        "Введите количество ребаев:",
        reply_markup=ReplyKeyboardRemove()  
    )
    return ADD_REBUYS

async def add_rebuys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data['rebuys'] = int(update.message.text)
        await update.message.reply_text("Введите стоимость бай-ина:")
        return ADD_BUYIN
    except ValueError:
        await update.message.reply_text("Введите число:")
        return ADD_REBUYS

async def add_buyin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data['buyin'] = float(update.message.text)
        await update.message.reply_text("Введите количество бобиков:")
        return ADD_BIG_BLIND
    except ValueError:
        await update.message.reply_text("Введите число:")
        return ADD_BUYIN

async def add_big_blind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data['big_blind'] = int(update.message.text)
        
        # Автоматический расчет банка
        players = context.user_data['players_count']
        rebuys = context.user_data['rebuys']
        buyin = context.user_data['buyin']
        bank = (players * buyin) + (rebuys * buyin)
        context.user_data['bank'] = round(bank, 2)
        
        await update.message.reply_text(
            f"Банк автоматически рассчитан: {context.user_data['bank']}\n"
            "Введите описание (необязательно, или отправьте '-' чтобы пропустить):",
            reply_markup=ReplyKeyboardRemove()  # Убираем клавиатуру
        )
        return ADD_DESCRIPTION
    except ValueError:
        await update.message.reply_text("Введите число:")
        return ADD_BIG_BLIND

async def add_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text if update.message.text != '-' else None
    
    game = PokerGame(
        date=context.user_data['game_date'],
        city=context.user_data['city'],
        players_count=context.user_data['players_count'],
        winner=context.user_data['winner'],
        second_place=context.user_data['second_place'],
        rebuys=context.user_data['rebuys'],
        bank=context.user_data['bank'],
        buyin=context.user_data['buyin'],
        big_blind=context.user_data['big_blind'],
        description=description
    )
    
    session.add(game)
    session.commit()
    
    await update.message.reply_text(
        "Игра успешно добавлена!\n"
        f"Дата: {game.date.strftime('%d.%m.%Y')}\n"
        f"Город: {game.city}\n"
        f"Игроков: {game.players_count}\n"
        f"Победитель: {game.winner}\n"
        f"2 место: {game.second_place}\n"
        f"Банк: {game.bank}",
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

async def show_recent_games(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    games = session.query(PokerGame).order_by(PokerGame.date.desc()).limit(5).all()
    
    if games:
        response = "Последние 5 игр:\n\n"
        for i, game in enumerate(games, 1):
            response += (
                f"{i}. {game.date.strftime('%d.%m.%Y')} - {game.city}\n"
                f"   Игроков: {game.players_count}\n"
                f"   Победитель: {game.winner}\n"
                f"   2 место: {game.second_place}\n\n"
            )
    else:
        response = "В базе пока нет игр."
    
    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

async def player_stats_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите имя игрока для статистики или 'все' для полной статистики:",
        reply_markup=ReplyKeyboardMarkup([[player] for player in PLAYERS] + [['все', 'Отмена']], resize_keyboard=True)
    )
    return PLAYER_STATS

async def show_player_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    player_name = update.message.text
    
    if player_name.lower() == 'все':
        return await show_all_stats(update, context)
    
    wins = session.query(PokerGame).filter(PokerGame.winner == player_name).order_by(PokerGame.date.desc()).all()
    seconds = session.query(PokerGame).filter(PokerGame.second_place == player_name).order_by(PokerGame.date.desc()).all()
    
    response = (
        f"📊 Статистика игрока {player_name}:\n"
        f"🏆 Побед: {len(wins)}\n"
        f"🥈 Вторых мест: {len(seconds)}\n\n"
    )
    
    if wins:
        response += "Последние победы:\n"
        for i, game in enumerate(wins[:3], 1):  # Показываем 3 последние победы
            response += (
                f"{i}. {game.date.strftime('%d.%m.%Y')} - {game.city}\n"
                f"   Банк: {game.bank}\n"
            )
        response += "\n"
    
    if seconds:
        response += "Последние 2 места:\n"
        for i, game in enumerate(seconds[:3], 1):  # Показываем 3 последних вторых места
            response += (
                f"{i}. {game.date.strftime('%d.%m.%Y')} - {game.city}\n"
                f"   Победитель: {game.winner}\n"
            )
    
    if not wins and not seconds:
        response += "Игр с участием этого игрока не найдено."
    
    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return MAIN_MENU

async def show_all_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    all_games = session.query(PokerGame).all()
    
    stats = {}
    for game in all_games:
        if game.winner not in stats:
            stats[game.winner] = {'wins': 0, 'seconds': 0}
        stats[game.winner]['wins'] += 1
        
        if game.second_place not in stats:
            stats[game.second_place] = {'wins': 0, 'seconds': 0}
        stats[game.second_place]['seconds'] += 1
    
    if not stats:
        await update.message.reply_text("В базе нет данных об играх.")
        return MAIN_MENU
    
    response = "📊 Общая статистика всех игроков:\n\n"
    for player, data in sorted(stats.items(), key=lambda x: (x[1]['wins'], x[1]['seconds']), reverse=True):
        response += (
            f"👤 *{player}*\n"
            f"🏆 Побед: {data['wins']} | "
            f"🥈 Вторых мест: {data['seconds']}\n\n"
        )
    
    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )
    return MAIN_MENU

async def search_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Введите дату игры (ДД.ММ.ГГГГ) или город для поиска:",
        reply_markup=ReplyKeyboardMarkup([['Отмена']], resize_keyboard=True)
    )
    return SEARCH_GAME

async def search_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    search_term = update.message.text
    
    try:
        search_date = datetime.strptime(search_term, '%d.%m.%Y').date()
        games = session.query(PokerGame).filter(PokerGame.date == search_date).all()
    except ValueError:
        games = session.query(PokerGame).filter(PokerGame.city.ilike(f"%{search_term}%")).all()
    
    if games:
        response = f"Найдено игр: {len(games)}\n\n"
        for game in games:
            response += (
                f"Дата: {game.date.strftime('%d.%m.%Y')}\n"
                f"Город: {game.city}\n"
                f"Игроков: {game.players_count}\n"
                f"Победитель: {game.winner}\n"
                f"2 место: {game.second_place}\n"
                f"Банк: {game.bank}\n"
                f"Количество ребаев: {game.rebuys}\n"
                f"Описание: {game.description}\n\n"
            )
    else:
        response = "Игр не найдено."
    
    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

def main() -> None:
    application = Application.builder().token("TOKEN").build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex('^Добавить игру$'), add_game_start),
                MessageHandler(filters.Regex('^Последние игры$'), show_recent_games),
                MessageHandler(filters.Regex('^Статистика игроков$'), player_stats_start),
                MessageHandler(filters.Regex('^Найти игру$'), search_game_start),
                MessageHandler(filters.Regex('^Удалить игру$'), delete_game_start),
            ],
            ADD_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_date),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            ADD_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_city),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            ADD_PLAYERS_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_players_count),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            ADD_WINNER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_winner),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            ADD_SECOND_PLACE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_second_place),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            ADD_REBUYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_rebuys),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            ADD_BUYIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_buyin),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            ADD_BIG_BLIND: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_big_blind),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            ADD_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_description),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            SEARCH_GAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_game),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            PLAYER_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, show_player_stats),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            DELETE_GAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_game_execute),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
            DELETE_GAME_SELECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_game_select),
                MessageHandler(filters.Regex('^Отмена$'), cancel),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('start', start),
            MessageHandler(filters.Regex('^Отмена$'), cancel),
        ],
    )
    
    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()