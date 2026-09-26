"""One-time, SQLite-only migration from the shared database to rooms.

Run this on the VPS while the containers are stopped. The script creates a
neighbouring backup before changing anything and never deletes that backup.
"""
import argparse
import hashlib
import secrets
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def invitation_code() -> str:
    return f"POKER-{secrets.token_urlsafe(16).upper()}"


def has_table(connection: sqlite3.Connection, name: str) -> bool:
    return bool(connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone())


def columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def migrate(database: Path, room_name: str, owner_telegram_id: str) -> str:
    connection = sqlite3.connect(database)
    try:
        if has_table(connection, "room_members"):
            raise RuntimeError("Миграция комнат уже была выполнена: найдена таблица room_members.")
        required = {"poker_games", "players", "game_players_association"}
        missing = [name for name in required if not has_table(connection, name)]
        if missing:
            raise RuntimeError(f"Это не похоже на базу Poker Stats, нет таблиц: {', '.join(missing)}")

        code = invitation_code()
        code_digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
        with connection:
            connection.execute("""
                CREATE TABLE rooms (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    code_hash VARCHAR(64) NOT NULL UNIQUE,
                    created_by_telegram_id VARCHAR(32) NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE room_members (
                    room_id INTEGER NOT NULL,
                    telegram_id VARCHAR(32) NOT NULL,
                    role VARCHAR(16) NOT NULL DEFAULT 'member',
                    PRIMARY KEY (room_id, telegram_id),
                    FOREIGN KEY(room_id) REFERENCES rooms(id)
                )
            """)
            cursor = connection.execute(
                "INSERT INTO rooms (name, code_hash, created_by_telegram_id) VALUES (?, ?, ?)",
                (room_name, code_digest, owner_telegram_id),
            )
            room_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO room_members (room_id, telegram_id, role) VALUES (?, ?, 'owner')",
                (room_id, owner_telegram_id),
            )

            game_columns = columns(connection, "poker_games")
            if "was_hookah" not in game_columns:
                connection.execute("ALTER TABLE poker_games ADD COLUMN was_hookah BOOLEAN NOT NULL DEFAULT 0")
            connection.execute("ALTER TABLE poker_games ADD COLUMN room_id INTEGER")
            connection.execute("UPDATE poker_games SET room_id = ?", (room_id,))
            connection.execute("CREATE INDEX ix_poker_games_room_id ON poker_games(room_id)")

            # SQLite cannot remove the old global UNIQUE(name) constraint with ALTER TABLE.
            connection.execute("ALTER TABLE game_players_association RENAME TO game_players_association_legacy")
            connection.execute("""
                CREATE TABLE players_new (
                    id INTEGER PRIMARY KEY,
                    room_id INTEGER NOT NULL,
                    name VARCHAR NOT NULL,
                    CONSTRAINT uq_players_room_name UNIQUE (room_id, name),
                    FOREIGN KEY(room_id) REFERENCES rooms(id)
                )
            """)
            connection.execute("INSERT INTO players_new (id, room_id, name) SELECT id, ?, name FROM players", (room_id,))
            connection.execute("DROP TABLE players")
            connection.execute("ALTER TABLE players_new RENAME TO players")
            connection.execute("CREATE INDEX ix_players_room_id ON players(room_id)")
            connection.execute("""
                CREATE TABLE game_players_association (
                    game_id INTEGER REFERENCES poker_games(id),
                    player_id INTEGER REFERENCES players(id)
                )
            """)
            connection.execute("""
                INSERT INTO game_players_association (game_id, player_id)
                SELECT game_id, player_id FROM game_players_association_legacy
            """)
            connection.execute("DROP TABLE game_players_association_legacy")

            if has_table(connection, "cities"):
                connection.execute("""
                    CREATE TABLE cities_new (
                        id INTEGER PRIMARY KEY,
                        room_id INTEGER NOT NULL,
                        name VARCHAR NOT NULL,
                        CONSTRAINT uq_cities_room_name UNIQUE (room_id, name),
                        FOREIGN KEY(room_id) REFERENCES rooms(id)
                    )
                """)
                connection.execute("INSERT INTO cities_new (id, room_id, name) SELECT id, ?, name FROM cities", (room_id,))
                connection.execute("DROP TABLE cities")
                connection.execute("ALTER TABLE cities_new RENAME TO cities")
            else:
                connection.execute("""
                    CREATE TABLE cities (
                        id INTEGER PRIMARY KEY,
                        room_id INTEGER NOT NULL,
                        name VARCHAR NOT NULL,
                        CONSTRAINT uq_cities_room_name UNIQUE (room_id, name),
                        FOREIGN KEY(room_id) REFERENCES rooms(id)
                    )
                """)
            connection.execute("CREATE INDEX ix_cities_room_id ON cities(room_id)")

            if has_table(connection, "season_metadata"):
                connection.execute("""
                    CREATE TABLE season_metadata_new (
                        room_id INTEGER NOT NULL,
                        start DATE NOT NULL,
                        title VARCHAR(120), image_data BLOB, image_mime VARCHAR(40),
                        PRIMARY KEY (room_id, start),
                        FOREIGN KEY(room_id) REFERENCES rooms(id)
                    )
                """)
                connection.execute("""
                    INSERT INTO season_metadata_new (room_id, start, title, image_data, image_mime)
                    SELECT ?, start, title, image_data, image_mime FROM season_metadata
                """, (room_id,))
                connection.execute("DROP TABLE season_metadata")
                connection.execute("ALTER TABLE season_metadata_new RENAME TO season_metadata")
            else:
                connection.execute("""
                    CREATE TABLE season_metadata (
                        room_id INTEGER NOT NULL, start DATE NOT NULL, title VARCHAR(120),
                        image_data BLOB, image_mime VARCHAR(40),
                        PRIMARY KEY (room_id, start), FOREIGN KEY(room_id) REFERENCES rooms(id)
                    )
                """)
        return code
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Move the existing shared Poker Stats history into one room.")
    parser.add_argument("database", type=Path, help="Path to poker_games.db on the VPS")
    parser.add_argument("--room-name", default="Наша покерная компания")
    parser.add_argument("--owner-telegram-id", required=True, help="Numeric Telegram ID of the room owner")
    parser.add_argument("--apply", action="store_true", help="Actually make the migration")
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_file():
        parser.error(f"Файл базы не найден: {database}")
    if not args.owner_telegram_id.isdigit():
        parser.error("--owner-telegram-id должен быть числовым Telegram ID")
    if not args.apply:
        print("Проверка пройдена. Повторите команду с --apply, чтобы выполнить миграцию.")
        return
    backup = database.with_name(f"{database.name}.pre-room-migration-{datetime.now():%Y%m%d-%H%M%S}.bak")
    shutil.copy2(database, backup)
    try:
        code = migrate(database, args.room_name, args.owner_telegram_id)
    except Exception:
        print(f"Миграция не завершилась. Оригинальная копия сохранена: {backup}", file=sys.stderr)
        raise
    print(f"Готово. Резервная копия: {backup}")
    print(f"Код доступа к исходной комнате (покажите участникам один раз): {code}")


if __name__ == "__main__":
    main()
