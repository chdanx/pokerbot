"""HTTP API for the Telegram Mini App."""
import hashlib
import hmac
import json
import os
import time
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import City, Player, PokerGame, get_session, init_db

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


class GamePayload(BaseModel):
    date: date
    city: str = Field(min_length=1, max_length=120)
    players_count: int = Field(ge=2, le=30)
    winner: str = Field(min_length=1, max_length=120)
    second_place: str = Field(min_length=1, max_length=120)
    participants: list[str] = Field(min_length=2, max_length=30)
    rebuys: int = Field(ge=0, le=100)
    buyin: float = Field(gt=0)
    big_blind: int = Field(gt=0)
    description: str | None = Field(default=None, max_length=2000)

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


def game_dict(game: PokerGame, detailed: bool = False) -> dict:
    result = {
        "id": game.id, "date": game.date.isoformat(), "city": game.city,
        "players_count": game.players_count, "winner": game.winner,
        "second_place": game.second_place, "bank": round(game.bank, 2),
        "rebuys": game.rebuys, "buyin": game.buyin, "big_blind": game.big_blind,
        "description": game.description,
    }
    if detailed:
        result["participants"] = sorted(player.name for player in game.players)
    return result


def game_averages(games: list[PokerGame]) -> dict:
    """Metrics that remain meaningful even when the game list is empty."""
    count = len(games)
    if not count:
        return {"games": 0, "bank": 0, "avg_bank": 0, "avg_players": 0, "avg_rebuys": 0, "avg_buyin": 0}
    return {
        "games": count,
        "bank": round(sum(game.bank for game in games), 2),
        "avg_bank": round(sum(game.bank for game in games) / count, 2),
        "avg_players": round(sum(game.players_count for game in games) / count, 1),
        "avg_rebuys": round(sum(game.rebuys for game in games) / count, 1),
        "avg_buyin": round(sum(game.buyin for game in games) / count, 2),
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


def save_game(payload: GamePayload, session: Session, game: PokerGame | None = None) -> PokerGame:
    if payload.winner == payload.second_place:
        raise HTTPException(422, "Winner and second place must be different")
    if len(payload.participants) != payload.players_count:
        raise HTTPException(422, "The number of participants must match players_count")
    if payload.winner not in payload.participants or payload.second_place not in payload.participants:
        raise HTTPException(422, "Winner and second place must be among participants")
    city_name = payload.city.strip()
    city = session.query(City).filter(func.lower(City.name) == city_name.lower()).one_or_none()
    if not city:
        city = City(name=city_name)
        session.add(city)
    game = game or PokerGame()
    game.date, game.city, game.players_count = payload.date, city.name, payload.players_count
    game.winner, game.second_place = payload.winner, payload.second_place
    game.rebuys, game.buyin, game.big_blind = payload.rebuys, payload.buyin, payload.big_blind
    game.bank = round((payload.players_count + payload.rebuys) * payload.buyin, 2)
    game.description = payload.description or None
    game.players.clear()
    for name in payload.participants:
        player = session.query(Player).filter_by(name=name).one_or_none()
        if not player:
            player = Player(name=name)
            session.add(player)
        game.players.append(player)
    session.add(game)
    session.commit()
    session.refresh(game)
    return game


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/bootstrap")
def bootstrap(_: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    games = session.query(PokerGame).order_by(PokerGame.date.desc(), PokerGame.id.desc()).limit(5).all()
    players = session.query(Player).order_by(Player.name).all()
    total_games = session.query(func.count(PokerGame.id)).scalar() or 0
    total_bank = session.query(func.coalesce(func.sum(PokerGame.bank), 0)).scalar()
    leaders = session.query(PokerGame.winner, func.count(PokerGame.id).label("wins")).group_by(PokerGame.winner).order_by(func.count(PokerGame.id).desc()).limit(3).all()
    return {"recent_games": [game_dict(game) for game in games], "players": [player.name for player in players],
            "cities": sorted({row[0] for row in session.query(PokerGame.city).all()} | {row[0] for row in session.query(City.name).all()}),
            "summary": {"games": total_games, "bank": round(total_bank, 2), "leaders": [{"name": name, "wins": wins} for name, wins in leaders]}}


@app.get("/api/games")
def games(
    search: str = "", city: str = "", winner: str = "", participant: str = "",
    date_from: date | None = None, date_to: date | None = None,
    limit: int = Query(50, le=100), _: dict = Depends(telegram_user), session: Session = Depends(db_session),
):
    query = session.query(PokerGame)
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
def game(game_id: int, _: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    item = session.get(PokerGame, game_id)
    if not item:
        raise HTTPException(404, "Game not found")
    return game_dict(item, detailed=True)


@app.post("/api/games", status_code=201)
def create_game(payload: GamePayload, _: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    return game_dict(save_game(payload, session), detailed=True)


@app.put("/api/games/{game_id}")
def update_game(game_id: int, payload: GamePayload, _: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    item = session.get(PokerGame, game_id)
    if not item:
        raise HTTPException(404, "Game not found")
    return game_dict(save_game(payload, session, item), detailed=True)


@app.delete("/api/games/{game_id}", status_code=204)
def delete_game(game_id: int, _: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    item = session.get(PokerGame, game_id)
    if not item:
        raise HTTPException(404, "Game not found")
    session.delete(item)
    session.commit()


@app.get("/api/players/{name}")
def player_stats(name: str, date_from: date | None = None, date_to: date | None = None, _: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    if not session.query(Player).filter(Player.name == name).one_or_none():
        raise HTTPException(404, "Player not found")
    query = session.query(PokerGame).join(PokerGame.players).filter(Player.name == name)
    all_games = query.order_by(PokerGame.date.desc(), PokerGame.id.desc()).all()
    if date_from:
        query = query.filter(PokerGame.date >= date_from)
    if date_to:
        query = query.filter(PokerGame.date <= date_to)
    games = query.order_by(PokerGame.date.desc(), PokerGame.id.desc()).all()
    season_start = date.fromisoformat(os.getenv("SEASON_START", "2025-06-01"))
    season_end = date.fromisoformat(os.getenv("SEASON_END", "2025-12-31"))
    duration = season_end - season_start
    previous_start, previous_end = season_start - duration - timedelta(days=1), season_start - timedelta(days=1)
    season_games = [game for game in all_games if season_start <= game.date <= season_end]
    previous_games = [game for game in all_games if previous_start <= game.date <= previous_end]
    return {"name": name, **player_summary(name, games), "recent_games": [game_dict(game) for game in games[:8]],
            "season_comparison": {"current": player_summary(name, season_games), "previous": player_summary(name, previous_games),
                                  "start": season_start.isoformat(), "end": season_end.isoformat()}}


@app.get("/api/stats")
def stats_overview(date_from: date | None = None, date_to: date | None = None, _: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    query = session.query(PokerGame)
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


@app.get("/api/season")
def season(_: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    start = date.fromisoformat(os.getenv("SEASON_START", "2025-06-01"))
    end = date.fromisoformat(os.getenv("SEASON_END", "2025-12-31"))
    games = session.query(PokerGame).filter(PokerGame.date.between(start, end)).all()
    names = sorted({player.name for game in games for player in game.players})
    board = []
    for name in names:
        played = [game for game in games if any(player.name == name for player in game.players)]
        wins = sum(game.winner == name for game in played)
        seconds = sum(game.second_place == name for game in played)
        points = (wins / len(played) * 100) + .33 * (seconds / len(played) * 100) if played else 0
        board.append({"name": name, "games": len(played), "wins": wins, "seconds": seconds, "points": round(points, 1)})
    return {"start": start.isoformat(), "end": end.isoformat(), "summary": game_averages(games),
            "leaderboard": sorted(board, key=lambda item: item["points"], reverse=True)}
