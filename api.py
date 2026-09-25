"""HTTP API for the Telegram Mini App."""
import hashlib
import hmac
import json
import os
import time
from datetime import date, datetime
from urllib.parse import parse_qsl

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import Player, PokerGame, get_session, init_db

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


def save_game(payload: GamePayload, session: Session, game: PokerGame | None = None) -> PokerGame:
    if payload.winner == payload.second_place:
        raise HTTPException(422, "Winner and second place must be different")
    if len(payload.participants) != payload.players_count:
        raise HTTPException(422, "The number of participants must match players_count")
    if payload.winner not in payload.participants or payload.second_place not in payload.participants:
        raise HTTPException(422, "Winner and second place must be among participants")
    game = game or PokerGame()
    game.date, game.city, game.players_count = payload.date, payload.city, payload.players_count
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
            "cities": sorted({row[0] for row in session.query(PokerGame.city).all()}),
            "summary": {"games": total_games, "bank": round(total_bank, 2), "leaders": [{"name": name, "wins": wins} for name, wins in leaders]}}


@app.get("/api/games")
def games(search: str = "", limit: int = Query(50, le=100), _: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    query = session.query(PokerGame)
    if search:
        term = f"%{search.strip()}%"
        filters = [PokerGame.city.ilike(term), PokerGame.winner.ilike(term), PokerGame.second_place.ilike(term)]
        try:
            filters.append(PokerGame.date == datetime.strptime(search, "%d.%m.%Y").date())
        except ValueError:
            pass
        query = query.filter(or_(*filters))
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
def player_stats(name: str, _: dict = Depends(telegram_user), session: Session = Depends(db_session)):
    games = session.query(PokerGame).join(PokerGame.players).filter(Player.name == name).order_by(PokerGame.date.desc()).all()
    if not games:
        raise HTTPException(404, "Player not found")
    wins = [game for game in games if game.winner == name]
    seconds = [game for game in games if game.second_place == name]
    return {"name": name, "games": len(games), "wins": len(wins), "seconds": len(seconds),
            "win_rate": round(len(wins) / len(games) * 100, 1), "bank_won": round(sum(game.bank for game in wins), 2),
            "recent_games": [game_dict(game) for game in games[:8]]}


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
    return {"start": start.isoformat(), "end": end.isoformat(), "leaderboard": sorted(board, key=lambda item: item["points"], reverse=True)}
