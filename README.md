# pokerbot
Это проект для небольшого круга друзей.
Мы очень любим играть с друзьями в покер. Я решил вести статистику по нашим играм. 
Чтобы статистика наших игр была у всех под рукой, я решил интегрировать это в telegram бота.

Используется Python 3.11.1, sqlite для манипулирования с базой данных.

## Запуск в Docker

1. Скопируйте пример переменных окружения:

```bash
cp .env.example .env
```

2. Укажите токен Telegram-бота в `.env`:

```bash
TELEGRAM_BOT_TOKEN=123456789:your_real_token
```

3. Запустите бота:

```bash
docker compose up -d --build
```

SQLite-база хранится в `./data/poker_games.db` и подключается в контейнер как volume. Для просмотра логов:

```bash
docker compose logs -f pokerbot
```

Для остановки:

```bash
docker compose down
```

## Переменные окружения

- `TELEGRAM_BOT_TOKEN` - обязательный токен Telegram-бота.
- `DATABASE_URL` - строка подключения SQLAlchemy. По умолчанию в Docker используется `sqlite:////app/data/poker_games.db`.
- `WELCOME_IMAGE_PATH` - путь к приветственной картинке. По умолчанию `/app/hi_pic.jpg` в Docker.
- `BOT_UID` и `BOT_GID` - UID/GID пользователя, от которого запускается контейнер. По умолчанию `1000:1000`, чтобы SQLite мог писать в bind mount `./data`.
