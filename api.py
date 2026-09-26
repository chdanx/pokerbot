"""HTTP API for the Telegram Mini App."""
import hashlib
import hmac
import json
import os
import time
import base64
import secrets
from datetime import date, datetime
from urllib.parse import parse_qsl

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import City, Player, PokerGame, Room, RoomMember, SeasonMetadata, get_session, init_db

FIRST_SEASON_START = date(2025, 1, 1)
FIRST_SEASON_END = date(2025, 5, 31)

app = FastAPI(title="Poker Stats API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin],
    allow_methods=["*"], allow_headers=["*"],
)


def db_session():
    session = get_session(init_db())
    try:
        yield session
    finally:
        session.close()


def telegram_user(x_telegram_init_data: str = Header(...)) -> dict:
    """Verify initData before trusting the Telegram user contained in it."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise HTTPException(500, "TELEGRAM_BOT_TOKEN is not configured")
    values = dict(parse_qsl(x_telegram_init_data, keep_blank_values=True))
    received_hash = values.pop("hash", None)
    auth_date = int(values.get("auth_date", "0"))
    if not received_hash or not auth_date or abs(time.time() - auth_date) > 86_400:
        raise HTTPException(401, "Telegram session has expired")
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(401, "Invalid Telegram session")
    try:
        return json.loads(values["user"])
    except (KeyError, json.JSONDecodeError) as error:
        raise HTTPException(401, "Telegram user is missing") from error


def telegram_id(user: dict) -> str:
    user_id = user.get("id")
    if user_id is None:
        raise HTTPException(401, "Telegram user id is missing")
    return str(user_id)


def room_access(
    x_room_id: int = Header(...), user: dict = Depends(telegram_user), session: Session = Depends(db_session),
) -> tuple[Room, RoomMember]:
    """Resolve the selected room only if the verified Telegram user belongs to it."""
    member = session.get(RoomMember, {"room_id": x_room_id, "telegram_id": telegram_id(user)})
    if not member:
        raise HTTPException(403, "Нет доступа к этой комнате")
    room = session.get(Room, x_room_id)
    if not room:
        raise HTTPException(404, "Комната не найдена")
    return room, member


class GamePayload(BaseModel):
    date: date
    city: str = Field(min_length=1, max_length=120)
    players_count: int = Field(ge=2, le=30)
    winner: str = Field(min_length=1, max_length=120)
    second_place: str = Field(min_length=1, max_length=120)
    participants: list[str] = Field(default_factory=list, max_length=30)
    rebuys: int = Field(ge=0, le=100)
    buyin: float = Field(gt=0)
    big_blind: float = Field(gt=0)
    was_hookah: bool = False
    beer_liters: float = Field(default=0, ge=0, le=100)
    description: str | None = Field(default=None, max_length=2000)
    is_archive: bool = False

    @field_validator("city")
    @classmethod
    def clean_city(cls, city: str) -> str:
        city = city.strip()
        if not city:
            raise ValueError("City must not be empty")
        return city

    @field_validator("participants")
    @classmethod
    def unique_participants(cls, players: list[str]) -> list[str]:
        cleaned = [player.strip() for player in players if player.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Participants must be unique")
        return cleaned

    @field_validator("beer_liters")
    @classmethod
    def half_liter_steps(cls, liters: float) -> float:
        if abs(liters * 2 - round(liters * 2)) > 1e-9:
            raise ValueError("Beer volume must use 0.5 liter steps")
        return liters


class PlayerPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Player name must not be empty")
        return name


class RoomPayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Название комнаты не должно быть пустым")
        return name


class JoinRoomPayload(BaseModel):
    code: str = Field(min_length=12, max_length=100)

    @field_validator("code")
    @classmethod
    def clean_code(cls, code: str) -> str:
        return code.strip().upper()


class SeasonMetadataPayload(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    image: str | None = Field(default=None, max_length=2_800_000)
    remove_image: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, title: str | None) -> str | None:
        return title.strip() if title and title.strip() else None


def game_dict(game: PokerGame, detailed: bool = False) -> dict:
    result = {
        "id": game.id, "date": game.date.isoformat(), "city": game.city,
        "players_count": game.players_count, "winner": game.winner,
        "second_place": game.second_place, "bank": round(game.bank, 2),
        "rebuys": game.rebuys, "buyin": game.buyin, "big_blind": game.big_blind,
        "was_hookah": game.was_hookah,
        "beer_liters": game.beer_liters,
        "description": game.description,
        "is_archive": game.is_archive,
    }
    if detailed:
        result["participants"] = sorted(player.name for player in game.players)
    return result


def room_dict(room: Room, member: RoomMember) -> dict:
    return {"id": room.id, "name": room.name, "role": member.role}


def room_code() -> str:
    # 128 bits of entropy: the invitation is a secret, not an identifier.
    return f"POKER-{secrets.token_urlsafe(16).upper()}"


def code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def game_averages(games: list[PokerGame]) -> dict:
    """Metrics that remain meaningful even when the game list is empty."""
    count = len(games)
    if not count:
        return {"games": 0, "bank": 0, "avg_bank": 0, "avg_players": 0, "avg_rebuys": 0, "hookah_sessions": 0, "beer_liters": 0}
    return {
        "games": count,
        "bank": round(sum(game.bank for game in games), 2),
        "avg_bank": round(sum(game.bank for game in games) / count, 2),
        "avg_players": round(sum(game.players_count for game in games) / count, 1),
        "avg_rebuys": round(sum(game.rebuys for game in games) / count, 1),
        "hookah_sessions": sum(bool(game.was_hookah) for game in games),
        "beer_liters": round(sum(game.beer_liters or 0 for game in games), 1),
    }


def player_summary(name: str, games: list[PokerGame]) -> dict:
    wins = [game for game in games if game.winner == name]
    seconds = [game for game in games if game.second_place == name]
    ordered = sorted(games, key=lambda game: (game.date, game.id))
    best_streak = current_streak = 0
    for game in ordered:
        if game.winner == name:
            current_streak += 1
            best_streak = max(best_streak, current_streak)
        else:
            current_streak = 0
    current_streak = 0
    for game in reversed(ordered):
        if game.winner != name:
            break
        current_streak += 1
    count = len(games)
    return {
        "games": count, "wins": len(wins), "seconds": len(seconds),
        "win_rate": round(len(wins) / count * 100, 1) if count else 0,
        "top2_rate": round((len(wins) + len(seconds)) / count * 100, 1) if count else 0,
        "bank_won": round(sum(game.bank for game in wins), 2),
        "best_win_streak": best_streak, "current_win_streak": current_streak,
        **{key: value for key, value in game_averages(games).items() if key not in {"games", "bank"}},
    }


def season_start_for(day: date) -> date:
    """Poker seasons run from Dec 1–May 31 and Jun 1–Nov 30."""
    if day <= FIRST_SEASON_END:
        return FIRST_SEASON_START
    if day.month in {12, 1, 2, 3, 4, 5}:
        return date(day.year if day.month == 12 else day.year - 1, 12, 1)
    return date(day.year, 6, 1)


def season_end_for(start: date) -> date:
    if start == FIRST_SEASON_START:
        return FIRST_SEASON_END
    return date(start.year + 1, 5, 31) if start.month == 12 else date(start.year, 11, 30)


def previous_season_start(start: date) -> date:
    if start == date(2025, 6, 1):
        return FIRST_SEASON_START
    return date(start.year, 6, 1) if start.month == 12 else date(start.year - 1, 12, 1)


def season_label(start: date) -> str:
    if start == FIRST_SEASON_START:
        return f"Начало статистики — {season_end_for(start).strftime('%d.%m.%Y')}"
    return f"{start.strftime('%d.%m.%Y')} — {season_end_for(start).strftime('%d.%m.%Y')}"


def season_data(session: Session, start: date, room_id: int) -> dict:
    end = season_end_for(start)
    date_filter = PokerGame.date <= end if start == FIRST_SEASON_START else PokerGame.date.between(start, end)
    games = session.query(PokerGame).filter(PokerGame.room_id == room_id, date_filter).all()
    names = sorted({player.name for game in games for player in game.players})
    board = []
    for name in names:
        played = [game for game in games if any(player.name == name for player in game.players)]
        wins = sum(game.winner == name for game in played)
        seconds = sum(game.second_place == name for game in played)
        points = (wins / len(played) * 100) + .33 * (seconds / len(played) * 100) if played else 0
        board.append({"name": name, "games": len(played), "wins": wins, "seconds": seconds, "points": round(points, 1)})
    leaderboard = sorted(board, key=lambda item: (-item["points"], -item["wins"], item["name"]))
    archive_games = [game for game in games if game.is_archive]
    archive_results: dict[str, dict] = {}
    for game in archive_games:
        for name, place in ((game.winner, "wins"), (game.second_place, "seconds")):
            result = archive_results.setdefault(name, {"name": name, "wins": 0, "seconds": 0})
            result[place] += 1
    archive_results_list = sorted(archive_results.values(), key=lambda item: (-item["wins"], -item["seconds"], item["name"]))
    metadata = session.get(SeasonMetadata, {"room_id": room_id, "start": start})
    return {"start": start.isoformat(), "end": end.isoformat(), "label": season_label(start),
            "title": metadata.title if metadata else None,
            "image_url": f"/api/seasons/{start.isoformat()}/image" if metadata and metadata.image_data else None,
            "summary": game_averages(games), "leaderboard": leaderboard,
            "archive_games": len(archive_games), "archive_results": archive_results_list}


def save_game(payload: GamePayload, session: Session, room_id: int, game: PokerGame | None = None) -> PokerGame:
    if payload.winner == payload.second_place:
        raise HTTPException(422, "Winner and second place must be different")
    if not payload.is_archive and len(payload.participants) != payload.players_count:
        raise HTTPException(422, "The number of participants must match players_count")
    if not payload.is_archive and (payload.winner not in payload.participants or payload.second_place not in payload.participants):
        raise HTTPException(422, "Winner and second place must be among participants")
    city_name = payload.city.strip()
    # SQLite's lower() only handles ASCII reliably, so it cannot be used for
    # Russian city names. Check the exact name first, then compare in Python.
    city = session.query(City).filter(City.room_id == room_id, City.name == city_name).one_or_none()
    if not city:
        city = next((item for item in session.query(City).filter_by(room_id=room_id).all() if item.name.casefold() == city_name.casefold()), None)
    if not city:
        city = City(room_id=room_id, name=city_name)
        session.add(city)
    game = game or PokerGame(room_id=room_id)
    game.date, game.city, game.players_count = payload.date, city.name, payload.players_count
    game.winner, game.second_place = payload.winner, payload.second_place
    game.rebuys, game.buyin, game.big_blind = payload.rebuys, payload.buyin, payload.big_blind
    game.was_hookah = payload.was_hookah
    game.beer_liters = payload.beer_liters
    game.is_archive = payload.is_archive
    game.bank = round((payload.players_count + payload.rebuys) * payload.buyin, 2)
    game.description = payload.description or None
    game.players.clear()
    for name in ([] if payload.is_archive else payload.participants):
        player = session.query(Player).filter_by(room_id=room_id, name=name).one_or_none()
        if not player:
            player = Player(room_id=room_id, name=name)
            session.add(player)
        game.players.append(player)
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/rooms")
def rooms(user: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    members = session.query(RoomMember).filter_by(telegram_id=telegram_id(user)).all()
    return [room_dict(member.room, member) for member in members]


@app.post("/api/rooms", status_code=201)
def create_room(payload: RoomPayload, user: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    user_id = telegram_id(user)
    code = room_code()
    room = Room(name=payload.name, code_hash=code_hash(code), created_by_telegram_id=user_id)
    session.add(room)
    session.flush()
    member = RoomMember(room_id=room.id, telegram_id=user_id, role="owner")
    session.add(member)
    session.commit()
    return {"room": room_dict(room, member), "code": code}


@app.post("/api/rooms/join")
def join_room(payload: JoinRoomPayload, user: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    room = session.query(Room).filter_by(code_hash=code_hash(payload.code)).one_or_none()
    if not room:
        raise HTTPException(404, "Комната с таким кодом не найдена")
    user_id = telegram_id(user)
    member = session.get(RoomMember, {"room_id": room.id, "telegram_id": user_id})
    if not member:
        member = RoomMember(room_id=room.id, telegram_id=user_id, role="member")
        session.add(member)
        session.commit()
    return {"room": room_dict(room, member)}


@app.post("/api/rooms/{room_id}/code")
def rotate_room_code(room_id: int, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    room, member = access
    if room.id != room_id:
        raise HTTPException(404, "Комната не найдена")
    if member.role != "owner":
        raise HTTPException(403, "Только владелец может сменить код")
    code = room_code()
    room.code_hash = code_hash(code)
    session.commit()
    return {"code": code}


@app.get("/api/bootstrap")
def bootstrap(access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    room_id = access[0].id
    games = session.query(PokerGame).filter_by(room_id=room_id).order_by(PokerGame.date.desc(), PokerGame.id.desc()).limit(5).all()
    players = session.query(Player).filter_by(room_id=room_id).order_by(Player.name).all()
    stats_games = session.query(PokerGame).filter(PokerGame.room_id == room_id, PokerGame.is_archive.is_(False))
    total_games = stats_games.with_entities(func.count(PokerGame.id)).scalar() or 0
    total_bank = stats_games.with_entities(func.coalesce(func.sum(PokerGame.bank), 0)).scalar()
    leaders = stats_games.with_entities(PokerGame.winner, func.count(PokerGame.id).label("wins")).group_by(PokerGame.winner).order_by(func.count(PokerGame.id).desc()).limit(3).all()
    return {"recent_games": [game_dict(game) for game in games], "players": [player.name for player in players],
            "cities": sorted({row[0] for row in session.query(PokerGame.city).filter_by(room_id=room_id).all()} | {row[0] for row in session.query(City.name).filter_by(room_id=room_id).all()}),
            "summary": {"games": total_games, "bank": round(total_bank, 2), "leaders": [{"name": name, "wins": wins} for name, wins in leaders]}}


@app.get("/api/games")
def games(
    search: str = "", city: str = "", winner: str = "", participant: str = "",
    date_from: date | None = None, date_to: date | None = None,
    limit: int = Query(50, le=100), access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session),
):
    query = session.query(PokerGame).filter(PokerGame.room_id == access[0].id)
    if search:
        term = f"%{search.strip()}%"
        filters = [PokerGame.city.ilike(term), PokerGame.winner.ilike(term), PokerGame.second_place.ilike(term)]
        try:
            filters.append(PokerGame.date == datetime.strptime(search, "%d.%m.%Y").date())
        except ValueError:
            pass
        query = query.filter(or_(*filters))
    if city:
        query = query.filter(PokerGame.city == city)
    if winner:
        query = query.filter(PokerGame.winner == winner)
    if participant:
        query = query.join(PokerGame.players).filter(Player.name == participant)
    if date_from:
        query = query.filter(PokerGame.date >= date_from)
    if date_to:
        query = query.filter(PokerGame.date <= date_to)
    return [game_dict(game) for game in query.order_by(PokerGame.date.desc(), PokerGame.id.desc()).limit(limit).all()]


@app.get("/api/games/{game_id}")
def game(game_id: int, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    item = session.query(PokerGame).filter_by(id=game_id, room_id=access[0].id).one_or_none()
    if not item:
        raise HTTPException(404, "Game not found")
    return game_dict(item, detailed=True)


@app.post("/api/games", status_code=201)
def create_game(payload: GamePayload, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    return game_dict(save_game(payload, session, access[0].id), detailed=True)


@app.put("/api/games/{game_id}")
def update_game(game_id: int, payload: GamePayload, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    item = session.query(PokerGame).filter_by(id=game_id, room_id=access[0].id).one_or_none()
    if not item:
        raise HTTPException(404, "Game not found")
    return game_dict(save_game(payload, session, access[0].id, item), detailed=True)


@app.delete("/api/games/{game_id}", status_code=204)
def delete_game(game_id: int, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    item = session.query(PokerGame).filter_by(id=game_id, room_id=access[0].id).one_or_none()
    if not item:
        raise HTTPException(404, "Game not found")
    session.delete(item)
    session.commit()


@app.post("/api/players", status_code=201)
def create_player(payload: PlayerPayload, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    room_id = access[0].id
    existing = session.query(Player).filter(Player.room_id == room_id, Player.name == payload.name).one_or_none()
    if not existing:
        existing = next((item for item in session.query(Player).filter_by(room_id=room_id).all() if item.name.casefold() == payload.name.casefold()), None)
    if existing:
        raise HTTPException(409, "Игрок с таким именем уже есть")
    player = Player(room_id=room_id, name=payload.name)
    session.add(player)
    session.commit()
    return {"name": player.name}


@app.get("/api/players/{name}")
def player_stats(name: str, date_from: date | None = None, date_to: date | None = None, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    room_id = access[0].id
    if not session.query(Player).filter(Player.room_id == room_id, Player.name == name).one_or_none():
        raise HTTPException(404, "Player not found")
    query = session.query(PokerGame).join(PokerGame.players).filter(PokerGame.room_id == room_id, Player.room_id == room_id, Player.name == name)
    all_games = query.order_by(PokerGame.date.desc(), PokerGame.id.desc()).all()
    if date_from:
        query = query.filter(PokerGame.date >= date_from)
    if date_to:
        query = query.filter(PokerGame.date <= date_to)
    games = query.order_by(PokerGame.date.desc(), PokerGame.id.desc()).all()
    season_start = season_start_for(date.today())
    season_end = season_end_for(season_start)
    previous_start = previous_season_start(season_start)
    previous_end = season_end_for(previous_start)
    season_games = [game for game in all_games if season_start <= game.date <= season_end]
    previous_games = [game for game in all_games if previous_start <= game.date <= previous_end]
    return {"name": name, **player_summary(name, games), "recent_games": [game_dict(game) for game in games[:8]],
            "season_comparison": {"current": player_summary(name, season_games), "previous": player_summary(name, previous_games),
                                  "start": season_start.isoformat(), "end": season_end.isoformat()}}


@app.get("/api/stats")
def stats_overview(date_from: date | None = None, date_to: date | None = None, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    query = session.query(PokerGame).filter(PokerGame.room_id == access[0].id, PokerGame.is_archive.is_(False))
    if date_from:
        query = query.filter(PokerGame.date >= date_from)
    if date_to:
        query = query.filter(PokerGame.date <= date_to)
    games = query.order_by(PokerGame.date.asc(), PokerGame.id.asc()).all()
    by_city: dict[str, list[PokerGame]] = {}
    by_month: dict[str, list[PokerGame]] = {}
    for game in games:
        by_city.setdefault(game.city, []).append(game)
        by_month.setdefault(game.date.strftime("%Y-%m"), []).append(game)
    cities = []
    for city_name, city_games in by_city.items():
        winners: dict[str, int] = {}
        for game in city_games:
            winners[game.winner] = winners.get(game.winner, 0) + 1
        leader, wins = max(winners.items(), key=lambda item: (item[1], item[0]))
        cities.append({"name": city_name, **game_averages(city_games), "leader": {"name": leader, "wins": wins}})
    months = [{"month": month, **game_averages(month_games)} for month, month_games in by_month.items()]
    biggest = max(games, key=lambda game: (game.bank, game.id), default=None)
    largest_wins: dict[str, PokerGame] = {}
    for game in games:
        current = largest_wins.get(game.winner)
        if not current or (game.bank, game.id) > (current.bank, current.id):
            largest_wins[game.winner] = game
    return {"period": {"date_from": date_from.isoformat() if date_from else None, "date_to": date_to.isoformat() if date_to else None},
            "summary": game_averages(games), "cities": sorted(cities, key=lambda item: (-item["games"], item["name"])),
            "months": months, "records": {"biggest_game": game_dict(biggest) if biggest else None,
            "largest_wins": [{"name": name, "game": game_dict(game)} for name, game in sorted(largest_wins.items(), key=lambda item: (-item[1].bank, item[0]))]}}


@app.get("/api/seasons")
def seasons(access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    """Short, tappable summaries of the current and completed poker seasons."""
    current_start = season_start_for(date.today())
    starts = {current_start}
    room_id = access[0].id
    for game_date, in session.query(PokerGame.date).filter_by(room_id=room_id).all():
        starts.add(season_start_for(game_date))
    metadata = {item.start: item for item in session.query(SeasonMetadata).filter_by(room_id=room_id).all()}
    summaries = []
    for start in sorted(starts, reverse=True):
        data = season_data(session, start, room_id)
        podium = [player for player in data["leaderboard"] if player["games"] >= 5][:2]
        item = metadata.get(start)
        summaries.append({"start": data["start"], "end": data["end"], "label": data["label"], "title": item.title if item else None,
                          "image_url": f"/api/seasons/{start.isoformat()}/image" if item and item.image_data else None, "summary": data["summary"],
                          "winner": podium[0] if podium else None, "second_place": podium[1] if len(podium) > 1 else None})
    return summaries


@app.get("/api/season")
def season(start: date | None = None, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    start = start or season_start_for(date.today())
    if start != season_start_for(start):
        raise HTTPException(422, "Season must start on 1 December or 1 June")
    return season_data(session, start, access[0].id)


@app.get("/api/seasons/{start}/image")
def season_image(start: date, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    metadata = session.get(SeasonMetadata, {"room_id": access[0].id, "start": start})
    if not metadata or not metadata.image_data:
        raise HTTPException(404, "Season image not found")
    return Response(metadata.image_data, media_type=metadata.image_mime or "image/jpeg")


@app.put("/api/seasons/{start}/metadata")
def update_season_metadata(start: date, payload: SeasonMetadataPayload, access: tuple[Room, RoomMember] = Depends(room_access), session: Session = Depends(db_session)):
    if start != season_start_for(start):
        raise HTTPException(422, "Season must start on 1 December, 1 June, or 1 January 2025")
    room_id = access[0].id
    metadata = session.get(SeasonMetadata, {"room_id": room_id, "start": start}) or SeasonMetadata(room_id=room_id, start=start)
    metadata.title = payload.title
    if payload.remove_image:
        metadata.image_data = metadata.image_mime = None
    if payload.image:
        try:
            header, encoded = payload.image.split(',', 1)
            mime = header.removeprefix('data:').removesuffix(';base64')
            image_data = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as error:
            raise HTTPException(422, "Invalid image") from error
        if mime not in {'image/jpeg', 'image/png', 'image/webp'} or not image_data or len(image_data) > 2_000_000:
            raise HTTPException(422, "Use a PNG, JPEG, or WebP image under 2 MB")
        metadata.image_data, metadata.image_mime = image_data, mime
    session.add(metadata)
    session.commit()
    return {"title": metadata.title, "image_url": f"/api/seasons/{start.isoformat()}/image" if metadata.image_data else None}
