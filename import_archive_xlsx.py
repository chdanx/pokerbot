"""Safely import the historical Kansas poker workbook as archive games.

The default is a dry run. Add --apply only after reviewing its report.
"""
import argparse
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from database import City, PokerGame, get_session, init_db

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Сокращения из исходной таблицы. Это только нормализация подписи результата:
# архивная игра по-прежнему не получает связи с таблицей игроков.
ARCHIVE_NAME_ALIASES = {
    "Даня Б": "Данила Бадецкий",
    "Слава Х": "Слава Харьков",
    "Богдан С": "Богдан Светоносов",
    "Дима Б": "Дмитрий Бедарев",
    "Дима Л": "Дмитрий Ляпин",
    "Макс М": "Максим Мерзлый",
    "МаксМ": "Максим Мерзлый",
    "Макс Г": "Максим Гомозов",
    "Сема": "Сема Попович",
    "Женя Ч": "Женя Черницкий",
    "Рома Р": "Рома Репняков",
    "Аня М": "Аня Маславская",
    "Даня 72": "Даня 72 Сергеев",
}


def read_sheet(path: Path):
    with zipfile.ZipFile(path) as book:
        strings = ["".join(item.itertext()) for item in ElementTree.fromstring(book.read("xl/sharedStrings.xml")).findall(NS + "si")]
        root = ElementTree.fromstring(book.read("xl/worksheets/sheet1.xml"))
    for row in root.findall(".//" + NS + "row"):
        values = {}
        for cell in row.findall(NS + "c"):
            value = cell.find(NS + "v")
            raw = "" if value is None else value.text
            if raw and cell.get("t") == "s":
                raw = strings[int(raw)]
            column = re.sub(r"\d", "", cell.get("r"))
            values[column] = raw or ""
        if values.get("A", "").replace(".0", "").isdigit() and values.get("B"):
            yield values


def number(value: str) -> float:
    found = re.search(r"\d+(?:[,.]\d+)?", value.replace(" ", ""))
    if not found:
        raise ValueError(f"не найдено число в {value!r}")
    return float(found.group().replace(",", "."))


def canonical_name(value: str) -> str:
    """Expand known abbreviations, including a shared second place such as 'МаксМ и Сема'."""
    parts = [part.strip() for part in value.strip().split(" и ")]
    return " и ".join(ARCHIVE_NAME_ALIASES.get(part, part) for part in parts)


def normalize(row: dict):
    required = {"B": "дата", "C": "город", "D": "игроки", "E": "победитель", "F": "второе место", "G": "ребаи", "H": "банк", "I": "бай-ин", "J": "блайнды"}
    absent = [label for key, label in required.items() if not row.get(key, "").strip()]
    if absent:
        raise ValueError("нет полей: " + ", ".join(absent))
    return {
        "source": f"kansas-stat:#{row['A'].replace('.0', '')}",
        "date": datetime.strptime(row["B"].strip(), "%d.%m.%Y").date(),
        "city": row["C"].strip(),
        "players_count": int(number(row["D"])),
        "winner": canonical_name(row["E"]),
        "second_place": canonical_name(row["F"]),
        "rebuys": int(number(row["G"])),
        "bank": number(row["H"]),
        "buyin": number(row["I"]),
        "big_blind": number(row["J"]),
        "description": row.get("K", "").strip() or None,
    }


def same_game(game: PokerGame, row: dict) -> bool:
    return (game.date == row["date"] and game.city.casefold() == row["city"].casefold()
            and game.winner.casefold() == row["winner"].casefold()
            and game.second_place.casefold() == row["second_place"].casefold()
            and abs((game.buyin or 0) - row["buyin"]) < 0.01)


def main():
    parser = argparse.ArgumentParser(description="Импорт архивных игр из poker Kansas stat.xlsx")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--room-id", type=int, required=True, help="ID комнаты из таблицы rooms")
    parser.add_argument("--apply", action="store_true", help="внести изменения; без флага только проверка")
    args = parser.parse_args()
    if not args.workbook.is_file():
        sys.exit(f"Файл не найден: {args.workbook}")

    session = get_session(init_db())
    try:
        existing = session.query(PokerGame).filter_by(room_id=args.room_id).all()
        added, converted, duplicate, invalid = [], [], [], []
        for source_row in read_sheet(args.workbook):
            number_label = source_row["A"].replace(".0", "")
            try:
                row = normalize(source_row)
            except ValueError as error:
                invalid.append((number_label, str(error)))
                continue
            source_match = next((game for game in existing if game.archive_source == row["source"]), None)
            game_match = next((game for game in existing if same_game(game, row)), None)
            if source_match or (game_match and game_match.is_archive):
                duplicate.append(number_label)
                continue
            if game_match:
                converted.append((game_match, row, number_label))
                continue
            added.append(row)

        print(f"Будет добавлено архивных игр: {len(added)}")
        print(f"Будет переведено в архив из обычных игр: {len(converted)}" + (f" (№ {', '.join(item[2] for item in converted)})" if converted else ""))
        print(f"Пропущено как уже имеющееся: {len(duplicate)}" + (f" (№ {', '.join(duplicate)})" if duplicate else ""))
        print(f"Пропущено из-за неполных данных: {len(invalid)}")
        for label, reason in invalid:
            print(f"  № {label}: {reason}")
        if not args.apply:
            print("Проверка завершена. БД не изменялась. Для импорта добавьте --apply.")
            return

        cities = {city.name.casefold(): city for city in session.query(City).filter_by(room_id=args.room_id).all()}
        def resolve_city(row):
            city = cities.get(row["city"].casefold())
            if not city:
                city = City(room_id=args.room_id, name=row["city"])
                session.add(city)
                cities[row["city"].casefold()] = city
            return city
        for game, row, _ in converted:
            city = resolve_city(row)
            for key, value in row.items():
                if key != "source":
                    setattr(game, key, city.name if key == "city" else value)
            game.is_archive = True
            game.archive_source = row["source"]
            game.players.clear()
        for row in added:
            city = resolve_city(row)
            game_fields = {key: value for key, value in row.items() if key not in {"source", "city"}}
            session.add(PokerGame(room_id=args.room_id, city=city.name, is_archive=True, archive_source=row["source"], **game_fields))
        session.commit()
        print(f"Импорт завершён: добавлено {len(added)}, переведено в архив {len(converted)}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
