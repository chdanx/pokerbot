from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile,
    InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, WebAppInfo
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from database import init_db, get_session, PokerGame, Player, generate_pie_chart_stats, game_players_association
from datetime import datetime
import logging
import os
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent
WELCOME_IMAGE_PATH = Path(os.getenv('WELCOME_IMAGE_PATH', BASE_DIR / 'hi_pic.jpg'))
WEB_APP_URL = os.getenv('WEB_APP_URL', '').strip()

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
            'Максим Гомозов', 'Богдан Светоносов', 'Евгений Черницкий', 'Роман Репняков',
              'Аня Маславская']

BTN_ADD_GAME = '➕ Добавить игру'
BTN_RECENT_GAMES = '🕘 Последние игры'
BTN_PLAYER_STATS = '📊 Статистика'
BTN_SEARCH_GAME = '🔎 Найти игру'
BTN_DELETE_GAME = '🗑 Удалить игру'
BTN_SEASONS = '🏆 Сезоны'
BTN_SEASON_POINTS = '🏅 Очки сезона'
BTN_MAIN_MENU = '🏠 Главное меню'
BTN_CANCEL = '❌ Отмена'
BTN_LIST = '📋 Список'
BTN_ALL_PLAYERS = '🌍 Все игроки'

PARTICIPANTS_REQUEST_START_DATE = datetime.strptime('27.05.2025', '%d.%m.%Y').date()

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
    PLAYER_STATS,
    ADD_PLAYERS,
    CONFIRM_PLAYERS,
    SEASONS_MENU,
    SEASON_POINTS,
) = range(19)

# Создаем клавиатуры
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [BTN_ADD_GAME, BTN_RECENT_GAMES],
        [BTN_PLAYER_STATS, BTN_SEARCH_GAME],
        [BTN_SEASONS, BTN_DELETE_GAME]
    ], resize_keyboard=True)

def get_seasons_keyboard():
    return ReplyKeyboardMarkup([
        [BTN_SEASON_POINTS],
        [BTN_MAIN_MENU]
    ], resize_keyboard=True)

def get_cities_keyboard():
    return ReplyKeyboardMarkup([[city] for city in CITIES] + [[BTN_CANCEL]], resize_keyboard=True)

def get_players_keyboard():
    return ReplyKeyboardMarkup([[player] for player in PLAYERS] + [[BTN_CANCEL]], resize_keyboard=True)

def is_cancel(text: str) -> bool:
    return text in {BTN_CANCEL, 'Отмена'}

async def check_cancel(update: Update, text: str) -> bool:
    if is_cancel(text):
        await update.message.reply_text(
            "Окей, отменил действие.\n\nВыберите следующий раздел в меню ниже.",
            reply_markup=get_main_keyboard()
        )
        return True
    return False

async def delete_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if 'delete_options' in context.user_data:
            del context.user_data['delete_options']
            
        await update.message.reply_text(
            "🗑 Удаление игры\n\nВведите дату в формате ДД.ММ.ГГГГ или откройте список последних игр.",
            reply_markup=ReplyKeyboardMarkup(
                [[BTN_LIST, BTN_CANCEL]],
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
        
        if is_cancel(text):
            return await cancel(update, context)
            
        if text in {BTN_LIST, 'Список'}:
            games = session.query(PokerGame).order_by(PokerGame.date.desc()).limit(5).all()
            if not games:
                await update.message.reply_text("Пока нет последних игр для удаления.")
                return MAIN_MENU
                
            keyboard = []
            context.user_data['delete_options'] = {}
            
            response = "🗑 Выберите игру для удаления:\n\n"
            for i, game in enumerate(games, 1):
                response += f"{i}. {game.date.strftime('%d.%m.%Y')} • {game.winner}\n"
                keyboard.append([str(i)])
                context.user_data['delete_options'][str(i)] = game.id
                
            keyboard.append([BTN_CANCEL])
            
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
                await update.message.reply_text("Игр на эту дату не найдено. Проверьте дату или выберите список.")
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
                    response += f"{i}. {game.winner} • банк {game.bank}\n"
                    
                await update.message.reply_text(
                    response,
                    reply_markup=ReplyKeyboardMarkup(
                        [[str(i)] for i in range(1, len(games)+1)] + [[BTN_CANCEL]],
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
        if is_cancel(update.message.text):
            return await cancel(update, context)
            
        if 'delete_options' not in context.user_data:
            await update.message.reply_text("Сессия устарела, начните заново")
            return MAIN_MENU
            
        choice = update.message.text.strip()
        if choice not in context.user_data['delete_options']:
            await update.message.reply_text("✏️ Выберите номер из списка")
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
    app_button = (
        InlineKeyboardMarkup([[InlineKeyboardButton('♠️ Открыть Poker Stats', web_app=WebAppInfo(url=WEB_APP_URL))]])
        if WEB_APP_URL else None
    )
    with WELCOME_IMAGE_PATH.open('rb') as photo:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=InputFile(photo),
            caption=(
                "♠️ Poker Stats\n\n"
                "Здесь живёт история ваших игр: результаты, банки, сезоны и личная статистика.\n"
                "Выберите действие в меню ниже."
            ),
            reply_markup=app_button or get_main_keyboard()
        )
    return MAIN_MENU


async def configure_menu_button(application: Application) -> None:
    """Expose the Mini App through Telegram's persistent menu button."""
    if WEB_APP_URL:
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text='Poker Stats', web_app=WebAppInfo(url=WEB_APP_URL))
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Окей, действие отменено.\n\nЧто делаем дальше?",
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

async def add_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Очищаем предыдущие данные
    context.user_data.clear()
    await update.message.reply_text(
        "➕ Новая игра\n\nВведите дату игры в формате ДД.ММ.ГГГГ.",
        reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)
    )
    return ADD_DATE

async def add_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, update.message.text):
        return MAIN_MENU

    try:
        date_obj = datetime.strptime(update.message.text, '%d.%m.%Y').date()
        context.user_data['game_date'] = date_obj
        await update.message.reply_text(
            "🏙 Выберите город, где прошла игра.",
            reply_markup=get_cities_keyboard()
        )
        return ADD_CITY
    except ValueError:
        await update.message.reply_text("Не узнал дату. Введите её так: 27.05.2025")
        return ADD_DATE

async def add_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, update.message.text):
        return MAIN_MENU
    
    if update.message.text not in CITIES:
        await update.message.reply_text("Выберите город кнопкой из списка ниже.")
        return ADD_CITY
    
    context.user_data['city'] = update.message.text
    await update.message.reply_text(
        "👥 Сколько игроков было за столом?",
        reply_markup=ReplyKeyboardRemove()  
    )
    return ADD_PLAYERS_COUNT

async def add_players_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, update.message.text):
        return MAIN_MENU
    
    try:
        players_count = int(update.message.text)
        if players_count < 2:
            await update.message.reply_text("Для игры нужно минимум 2 игрока. Введите число ещё раз.")
            return ADD_PLAYERS_COUNT
            
        context.user_data['players_count'] = players_count
        await update.message.reply_text(
            "🏆 Кто забрал первое место?",
            reply_markup=get_players_keyboard()
        )
        return ADD_WINNER
    except ValueError:
        await update.message.reply_text("Введите количество игроков числом.")
        return ADD_PLAYERS_COUNT

async def add_winner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, update.message.text):
        return MAIN_MENU
    
    if update.message.text not in PLAYERS:
        await update.message.reply_text("Выберите игрока кнопкой из списка ниже.")
        return ADD_WINNER
    
    context.user_data['winner'] = update.message.text
    await update.message.reply_text(
        "🥈 Кто занял второе место?",
        reply_markup=get_players_keyboard()
    )
    return ADD_SECOND_PLACE

async def add_second_place(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, update.message.text):
        return MAIN_MENU
    
    if update.message.text not in PLAYERS:
        await update.message.reply_text("Выберите игрока кнопкой из списка ниже.")
        return ADD_SECOND_PLACE

    context.user_data['second_place'] = update.message.text

    # Проверяем, нужно ли запрашивать участников
    if context.user_data['game_date'] >= PARTICIPANTS_REQUEST_START_DATE:
        available_players = [player for player in PLAYERS if player not in [context.user_data['winner'], context.user_data['second_place']]]
        keyboard = ReplyKeyboardMarkup([[player] for player in available_players] + [[BTN_CANCEL]], resize_keyboard=True)
        await update.message.reply_text("👤 Выберите остальных участников игры.", reply_markup=keyboard)
        return CONFIRM_PLAYERS
    else:
        # Для старых игр просто переходим к следующему шагу
        await update.message.reply_text("🔄 Сколько было ребаев?")
        return ADD_REBUYS


async def add_players(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, update.message.text):
        return MAIN_MENU
    
    context.user_data['selected_players'] = []

    # Исключаем победителя и игрока, занявшего второе место, из списка доступных участников
    available_players = [player for player in PLAYERS if player not in [context.user_data['winner'], context.user_data['second_place']]]

    keyboard = ReplyKeyboardMarkup([[player] for player in available_players] + [[BTN_CANCEL]], resize_keyboard=True)

    await update.message.reply_text(
        "👤 Выберите участников игры.",
        reply_markup=keyboard
    )
    return CONFIRM_PLAYERS


async def confirm_players(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected_player = update.message.text

    if await check_cancel(update, selected_player):
        return MAIN_MENU

    if selected_player not in PLAYERS:
        await update.message.reply_text("Выберите игрока кнопкой из списка ниже.")
        return CONFIRM_PLAYERS

    if 'selected_players' not in context.user_data:
        context.user_data['selected_players'] = []

    if selected_player not in context.user_data['selected_players']:
        context.user_data['selected_players'].append(selected_player)

    # Проверяем, выбрано ли достаточное количество участников
    total_players = len(context.user_data['selected_players']) + 2  # +2 для победителя и второго места
    if total_players >= context.user_data['players_count']:
        await update.message.reply_text(
            f"✅ Участники выбраны: {', '.join(context.user_data['selected_players'])}\n\n"
            "🔄 Сколько было ребаев?",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_REBUYS

    available_players = [player for player in PLAYERS if player not in [context.user_data['winner'], context.user_data['second_place']] + context.user_data['selected_players']]

    keyboard = ReplyKeyboardMarkup([[player] for player in available_players] + [[BTN_CANCEL]], resize_keyboard=True)

    await update.message.reply_text(
        f"Уже выбраны: {', '.join(context.user_data['selected_players'])}\n\n"
        "Выберите ещё одного участника.",
        reply_markup=keyboard
    )
    return CONFIRM_PLAYERS

async def players_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == 'Готово':
        await update.message.reply_text(
            f"✅ Участники выбраны: {', '.join(context.user_data['selected_players'])}\n\n"
            "🔄 Сколько было ребаев?",
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_REBUYS
    else:
        return await confirm_players(update, context)

async def add_rebuys(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, update.message.text):
        return MAIN_MENU

    try:
        context.user_data['rebuys'] = int(update.message.text)
        await update.message.reply_text("🎫 Какая была стоимость бай-ина?")
        return ADD_BUYIN
    except ValueError:
        await update.message.reply_text("Введите количество ребаев числом.")
        return ADD_REBUYS

async def add_buyin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, update.message.text):
        return MAIN_MENU

    try:
        context.user_data['buyin'] = float(update.message.text)
        await update.message.reply_text("♠️ Введите большой блайнд.")
        return ADD_BIG_BLIND
    except ValueError:
        await update.message.reply_text("Введите бай-ин числом, например 500 или 500.0.")
        return ADD_BUYIN

async def add_big_blind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, update.message.text):
        return MAIN_MENU

    try:
        context.user_data['big_blind'] = int(update.message.text)
        
        # Автоматический расчет банка
        players = context.user_data['players_count']
        rebuys = context.user_data['rebuys']
        buyin = context.user_data['buyin']
        bank = (players * buyin) + (rebuys * buyin)
        context.user_data['bank'] = round(bank, 2)
        
        await update.message.reply_text(
            f"💰 Банк рассчитан: {context.user_data['bank']}\n\n"
            "Добавьте короткое описание или отправьте '-' чтобы пропустить.",
            reply_markup=ReplyKeyboardRemove()  # Убираем клавиатуру
        )
        return ADD_DESCRIPTION
    except ValueError:
        await update.message.reply_text("Введите большой блайнд числом.")
        return ADD_BIG_BLIND

async def add_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, update.message.text):
        return MAIN_MENU

    description = update.message.text if update.message.text != '-' else None

    # Создаем игру
    game = PokerGame(
        date=context.user_data['game_date'],
        city=context.user_data['city'],
        players_count=context.user_data['players_count'],  # Сохраняем введенное количество игроков
        winner=context.user_data['winner'],
        second_place=context.user_data['second_place'],
        rebuys=context.user_data['rebuys'],
        bank=context.user_data['bank'],
        buyin=context.user_data['buyin'],
        big_blind=context.user_data['big_blind'],
        description=description
    )

    # Для игр после определенной даты добавляем участников
    if context.user_data['game_date'] >= PARTICIPANTS_REQUEST_START_DATE:
        selected_players = context.user_data.get('selected_players', [])
        all_players = selected_players + [context.user_data['winner'], context.user_data['second_place']]
        
        # Проверяем соответствие количества
        if len(all_players) != context.user_data['players_count']:
            await update.message.reply_text(
                f"Не сходится количество участников: выбрано {len(all_players)}, указано {context.user_data['players_count']}.",
                reply_markup=get_main_keyboard()
            )
            return MAIN_MENU

        # Добавляем игроков в игру
        for player_name in all_players:
            player = session.query(Player).filter_by(name=player_name).first()
            if not player:
                player = Player(name=player_name)
                session.add(player)
            game.players.append(player)
    else:
        # Для старых игр просто добавляем победителя и второго места
        for player_name in [context.user_data['winner'], context.user_data['second_place']]:
            player = session.query(Player).filter_by(name=player_name).first()
            if not player:
                player = Player(name=player_name)
                session.add(player)
            game.players.append(player)

    session.add(game)
    session.commit()

    # Формируем сообщение
    response = (
        "✅ Игра сохранена\n\n"
        f"📅 Дата: {game.date.strftime('%d.%m.%Y')}\n"
        f"🏙 Город: {game.city}\n"
        f"👥 Игроков: {game.players_count}\n"
        f"🏆 Победитель: {game.winner}\n"
        f"🥈 Второе место: {game.second_place}\n"
        f"🔄 Ребаев: {game.rebuys}\n"
        f"🎫 Бай-ин: {game.buyin}\n"
        f"♠️ ББ: {game.big_blind}\n"
        f"💰 Банк: {game.bank}\n"
    )

    if context.user_data['game_date'] >= PARTICIPANTS_REQUEST_START_DATE:
        response += f"\n👤 Участники: {', '.join([p.name for p in game.players])}\n"

    if game.description:
        response += f"\n📝 {game.description}\n"

    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU


async def show_recent_games(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    games = session.query(PokerGame).order_by(PokerGame.date.desc()).limit(5).all()
    
    if games:
        response = "🕘 Последние 5 игр\n\n"
        for i, game in enumerate(games, 1):
            response += (
                f"{i}. {game.date.strftime('%d.%m.%Y')} • {game.city}\n"
                f"   👥 {game.players_count} игроков\n"
                f"   🏆 {game.winner}\n"
                f"   🥈 {game.second_place}\n\n"
            )
    else:
        response = "Пока нет сохранённых игр. Самое время добавить первую."
    
    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

async def player_stats_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📊 Статистика\n\nВыберите игрока или откройте общий обзор.",
        reply_markup=ReplyKeyboardMarkup([[BTN_ALL_PLAYERS]] + [[player] for player in PLAYERS] + [[BTN_CANCEL]], resize_keyboard=True)
    )
    return PLAYER_STATS

async def seasons_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🏆 Сезоны\n\n"
        "🍀 Первый сезон: Лакерный\n"
        "📅 До 31.05.2025\n"
        "🏆 Победитель: Слава Харьков\n"
        "🥈 Преследователь: Данила Бадецкий\n\n"
        "Второй сезон: \n"
        "📅 С 01.06.2025 До 31.12.2025\n"
        "Победитель: \n"
        "Преследователь: \n\n"
        "Третий сезон \n"
        "Откройте очки текущего сезона кнопкой ниже.",
        reply_markup=get_seasons_keyboard()
    )
    return SEASONS_MENU

async def show_season_points(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    SEASON_START_DATE = datetime.strptime('01.06.2025', '%d.%m.%Y').date()
    SEASON_END_DATE = datetime.strptime('30.11.2025', '%d.%m.%Y').date()
    
    # Получаем всех игроков
    players = session.query(Player).all()
    player_stats = []
    
    for player in players:
        # Получаем игры сезона с участием игрока
        season_games = session.query(PokerGame)\
            .join(PokerGame.players)\
            .filter(
                Player.id == player.id,
                PokerGame.date >= SEASON_START_DATE,
                PokerGame.date <= SEASON_END_DATE
            ).all()
        
        if not season_games:
            continue
            
        # Считаем статистику
        wins = len([g for g in season_games if g.winner == player.name])
        seconds = len([g for g in season_games if g.second_place == player.name])
        total_games = len(season_games)
        
        win_rate = (wins / total_games * 100) if total_games > 0 else 0
        second_rate = (seconds / total_games * 100) if total_games > 0 else 0
        
        # Рассчитываем очки по формуле
        points = win_rate + 0.33 * second_rate
        player_stats.append((player.name, points, wins, seconds, total_games))
    
    # Сортируем по убыванию очков
    player_stats.sort(key=lambda x: x[1], reverse=True)
    
    # Формируем ответ (без Markdown разметки)
    response = "🏅 Очки сезона\n\n"
    response += "Формула: победы + 0.33 × вторые места\n"
    response += "Формат: очки / победы / вторые места / игры\n\n"
    
    for i, (name, points, wins, seconds, total) in enumerate(player_stats, 1):
        win_rate = (wins / total * 100) if total > 0 else 0
        second_rate = (seconds / total * 100) if total > 0 else 0
        medal = '🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'{i}.'
        response += f"{medal} {name}: {points:.1f} / {wins} / {seconds} / {total}\n"
    
    if not player_stats:
        response = "В текущем сезоне ещё не было игр."
    
    await update.message.reply_text(
        response,
        reply_markup=get_seasons_keyboard(),
        parse_mode=None  
    )
    return SEASONS_MENU

async def show_player_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    player_name = update.message.text

    if await check_cancel(update, update.message.text):
        return MAIN_MENU

    if player_name.lower() == 'все' or player_name == BTN_ALL_PLAYERS:
        return await show_all_stats(update, context)

    # Определяем даты начала и конца сезона
    SEASON_START_DATE = datetime.strptime('01.06.2025', '%d.%m.%Y').date()
    SEASON_END_DATE = datetime.strptime('30.11.2025', '%d.%m.%Y').date()

    # Получаем все игры игрока
    games_participated = session.query(PokerGame).join(PokerGame.players).filter(
        Player.name == player_name
    ).order_by(PokerGame.date.desc()).all()

    # Статистика за все время
    wins_all = [game for game in games_participated if game.winner == player_name]
    seconds_all = [game for game in games_participated if game.second_place == player_name]
    total_bank_won_all = sum(game.bank for game in wins_all)

    # Статистика за сезон
    season_games = [game for game in games_participated if SEASON_START_DATE <= game.date <= SEASON_END_DATE]
    season_wins = [game for game in season_games if game.winner == player_name]
    season_seconds = [game for game in season_games if game.second_place == player_name]
    season_top2 = len(season_wins) + len(season_seconds)
    season_bank = sum(game.bank for game in season_wins)

    # Рассчитываем проценты для сезона
    season_win_rate_top2 = (season_top2 / len(season_games) * 100) if season_games else 0
    season_win_rate = (len(season_wins) / len(season_games) * 100) if season_games else 0

    # Формируем ответ
    response = (
        f"📊 {player_name}\n\n"
        "За всё время\n"
        f"🏆 Побед: {len(wins_all)}\n"
        f"🥈 Вторых мест: {len(seconds_all)}\n"
        f"💰 Выигранный банк: {total_bank_won_all}\n\n"
        f"Сезон {SEASON_START_DATE.strftime('%d.%m.%Y')} - {SEASON_END_DATE.strftime('%d.%m.%Y')}\n"
        f"🎲 Игр: {len(season_games)}\n"
        f"🏆 Побед: {len(season_wins)}\n"
        f"🥈 Вторых мест: {len(season_seconds)}\n"
        f"🎯 Топ-2: {season_top2}/{len(season_games)}\n"
        f"📈 Топ-2 rate: {season_win_rate_top2:.2f}%\n"
        f"📈 Winrate: {season_win_rate:.2f}%\n"
        f"💰 Банк сезона: {season_bank}\n\n"
    )

    # Добавляем последние победы
    if wins_all:
        response += "🏆 Последние победы\n"
        for i, game in enumerate(wins_all[:3], 1):
            response += (
                f"{i}. {game.date.strftime('%d.%m.%Y')} • {game.city} • банк {game.bank}\n"
            )
        response += "\n"

    # Добавляем последние победы в сезоне
    if seconds_all:
        response += "🥈 Последние вторые места\n"
        for i, game in enumerate(seconds_all[:3], 1):
            response += (
                f"{i}. {game.date.strftime('%d.%m.%Y')} • {game.city} • победитель {game.winner}\n"
            )

    if not games_participated:
        response = f"Не нашёл игрока {player_name} в базе."

    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard(),
        parse_mode=None
    )
    return MAIN_MENU

async def show_all_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    all_games = session.query(PokerGame).all()

    img_buffer = generate_pie_chart_stats()

    stats = {}
    for game in all_games:
        for player in game.players:
            if player.name not in stats:
                stats[player.name] = {'wins_all': 0, 'seconds_all': 0, 'total_bank_won_all': 0, 'wins': 0, 'seconds': 0, 'total_games': 0, 'total_bank_won': 0}

            # Считаем победы, вторые места и банк по всем играм
            if game.winner == player.name:
                stats[player.name]['wins_all'] += 1
                stats[player.name]['total_bank_won_all'] += game.bank
            if game.second_place == player.name:
                stats[player.name]['seconds_all'] += 1

            # Считаем попадания в топ 2 и винрейты только с указанной даты
            if game.date >= PARTICIPANTS_REQUEST_START_DATE:
                stats[player.name]['total_games'] += 1

                if game.winner == player.name:
                    stats[player.name]['wins'] += 1
                    stats[player.name]['total_bank_won'] += game.bank
                elif game.second_place == player.name:
                    stats[player.name]['seconds'] += 1

    if not stats:
        await update.message.reply_text("В базе нет данных об играх.")
        return MAIN_MENU

    response = "🌍 Общая статистика\n\n"
    for player, data in sorted(stats.items(), key=lambda x: (x[1]['wins'], x[1]['seconds']), reverse=True):
        total_top2 = data['wins'] + data['seconds']
        win_rate_top2 = (total_top2 / data['total_games'] * 100) if data['total_games'] > 0 else 0
        win_rate_wins = (data['wins'] / data['total_games'] * 100) if data['total_games'] > 0 else 0

        response += (
            f"👤 {player}\n"
            f"🏆 Побед: {data['wins_all']} | "
            f"🥈 Вторых мест: {data['seconds_all']}\n"
            f"💰 Выигранный банк: {data['total_bank_won_all']}\n\n"
            # "Актуальная статистика для игр после 27 мая 2025 года:\n"
            # f"🎯 Попаданий в топ 2: {total_top2}/{data['total_games']}\n"
            # f"📈 Винрейт (топ 2): {win_rate_top2:.2f}% | "
            # f"📈 Винрейт (победы): {win_rate_wins:.2f}%\n\n"
        )
    
    response += "Выберите конкретного игрока, чтобы увидеть подробную карточку.\n"

    await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=img_buffer,
            caption="💰 Распределение выигранных банков",
            reply_markup=get_main_keyboard()
        )

    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard(),
        parse_mode=None
    )
    return MAIN_MENU

async def search_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔎 Поиск игры\n\nВведите дату в формате ДД.ММ.ГГГГ или название города.",
        reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)
    )
    return SEARCH_GAME

async def search_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    search_term = update.message.text

    if await check_cancel(update, search_term):
        return MAIN_MENU
    
    try:
        search_date = datetime.strptime(search_term, '%d.%m.%Y').date()
        games = session.query(PokerGame).filter(PokerGame.date == search_date).all()
    except ValueError:
        games = session.query(PokerGame).filter(PokerGame.city.ilike(f"%{search_term}%")).all()
    
    if not games:
        await update.message.reply_text(
            "Ничего не нашёл. Попробуйте другую дату или город.",
            reply_markup=get_main_keyboard()
        )
        return MAIN_MENU
    
    for game in games:
        # Получаем участников игры через связь many-to-many
        participants = session.query(Player).\
            join(game_players_association).\
            join(PokerGame).\
            filter(PokerGame.id == game.id).\
            all()
        
        # Формируем информацию об игре
        response = (
            "🎲 Карточка игры\n\n"
            f"📅 Дата: {game.date.strftime('%d.%m.%Y')}\n"
            f"🏙 Город: {game.city}\n"
            f"👥 Игроков: {game.players_count}\n"
            f"🏆 Победитель: {game.winner}\n"
            f"🥈 Второе место: {game.second_place}\n"
            f"💰 Банк: {game.bank:.2f}\n"
            f"🔄 Ребаев: {game.rebuys}\n"
            f"🎫 Бай-ин: {game.buyin:.2f}\n"
            f"♠️ ББ: {game.big_blind}\n"
        )
        if game.date >= PARTICIPANTS_REQUEST_START_DATE:
            # Добавляем список участников, если они есть
            if participants:
                response += "\n👤 Участники\n"
                for player in participants:
                    # Добавляем эмодзи для победителя и второго места
                    if player.name == game.winner:
                        response += f"👑 {player.name}\n"
                    elif player.name == game.second_place:
                        response += f"🥈 {player.name}\n"
                    else:
                        response += f"👤 {player.name}\n"
        
        # Добавляем описание, если оно есть
        if game.description:
            response += f"\n📝 Описание: {game.description}\n"
        
        # Отправляем сообщение для каждой игры
        await update.message.reply_text(
            response,
            reply_markup=get_main_keyboard(),
            parse_mode=None
        )
    
    return MAIN_MENU

def main() -> None:
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN environment variable is required')

    application = Application.builder().token(token).post_init(configure_menu_button).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                MessageHandler(filters.Regex(f'^({BTN_ADD_GAME}|Добавить игру)$'), add_game_start),
                MessageHandler(filters.Regex(f'^({BTN_RECENT_GAMES}|Последние игры)$'), show_recent_games),
                MessageHandler(filters.Regex(f'^({BTN_PLAYER_STATS}|Статистика игроков|Статистика)$'), player_stats_start),
                MessageHandler(filters.Regex(f'^({BTN_SEARCH_GAME}|Найти игру)$'), search_game_start),
                MessageHandler(filters.Regex(f'^({BTN_DELETE_GAME}|Удалить игру)$'), delete_game_start),
                MessageHandler(filters.Regex(f'^({BTN_SEASONS}|Сезоны)$'), seasons_menu),
            ],
            ADD_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_date),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            ADD_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_city),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            ADD_PLAYERS_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_players_count),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            ADD_WINNER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_winner),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            ADD_SECOND_PLACE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_second_place),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            ADD_PLAYERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_players),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            CONFIRM_PLAYERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_players),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            ADD_REBUYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_rebuys),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            ADD_BUYIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_buyin),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            ADD_BIG_BLIND: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_big_blind),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            ADD_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_description),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            SEARCH_GAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_game),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            PLAYER_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, show_player_stats),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            DELETE_GAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_game_execute),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            DELETE_GAME_SELECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_game_select),
                MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
            ],
            SEASONS_MENU: [
                MessageHandler(filters.Regex(f'^({BTN_SEASON_POINTS}|Очки сезона)$'), show_season_points),
                MessageHandler(filters.Regex(f'^({BTN_MAIN_MENU}|Вернуться в главное меню)$'), cancel),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('start', start),
            MessageHandler(filters.Regex(f'^({BTN_CANCEL}|Отмена)$'), cancel),
        ],
    )
    
    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()
