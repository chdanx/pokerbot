import os

from sqlalchemy import create_engine, Column, Integer, String, Date, Float, Boolean, ForeignKey, LargeBinary, Table, func, inspect, text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import date
import matplotlib.pyplot as plt
import io

Base = declarative_base()

# Таблица для связи между играми и участниками
game_players_association = Table(
    'game_players_association',
    Base.metadata,
    Column('game_id', Integer, ForeignKey('poker_games.id')),
    Column('player_id', Integer, ForeignKey('players.id'))
)

class Player(Base):
    __tablename__ = 'players'

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('rooms.id'), nullable=False, index=True)
    name = Column(String, nullable=False)

    __table_args__ = (UniqueConstraint('room_id', 'name', name='uq_players_room_name'),)


class City(Base):
    __tablename__ = 'cities'

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('rooms.id'), nullable=False, index=True)
    name = Column(String, nullable=False)

    __table_args__ = (UniqueConstraint('room_id', 'name', name='uq_cities_room_name'),)


class Room(Base):
    __tablename__ = 'rooms'

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    code_hash = Column(String(64), nullable=False, unique=True)
    created_by_telegram_id = Column(String(32), nullable=False)


class RoomMember(Base):
    __tablename__ = 'room_members'

    room_id = Column(Integer, ForeignKey('rooms.id'), primary_key=True)
    telegram_id = Column(String(32), primary_key=True)
    role = Column(String(16), nullable=False, default='member')

    room = relationship('Room', backref='members')

class PokerGame(Base):
    __tablename__ = 'poker_games'

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('rooms.id'), nullable=False, index=True)
    date = Column(Date, default=date.today())
    city = Column(String)
    players_count = Column(Integer)
    winner = Column(String)
    second_place = Column(String)
    rebuys = Column(Integer)
    bank = Column(Float)
    buyin = Column(Float)
    big_blind = Column(Integer)
    was_hookah = Column(Boolean, nullable=False, default=False)
    description = Column(String, nullable=True)

    # Связь с участниками
    players = relationship("Player", secondary=game_players_association, backref="poker_games")


class SeasonMetadata(Base):
    __tablename__ = 'season_metadata'

    room_id = Column(Integer, ForeignKey('rooms.id'), primary_key=True)
    start = Column(Date, primary_key=True)
    title = Column(String(120), nullable=True)
    image_data = Column(LargeBinary, nullable=True)
    image_mime = Column(String(40), nullable=True)

def init_db():
    database_url = os.getenv('DATABASE_URL', 'sqlite:///data/poker_games.db')
    engine = create_engine(database_url)
    # Do not let a new application version partially initialise a legacy
    # database. The explicit migration keeps the existing history intact.
    if engine.dialect.name == 'sqlite' and inspect(engine).has_table('poker_games'):
        columns = {column['name'] for column in inspect(engine).get_columns('poker_games')}
        if 'room_id' not in columns:
            raise RuntimeError('Legacy database detected. Run migrate_rooms.py before starting the application.')
    Base.metadata.create_all(engine)
    # SQLite's create_all does not add a new column to an existing production table.
    # Keep this small migration here so the deployed database gains the hookah flag safely.
    if engine.dialect.name == 'sqlite':
        columns = {column['name'] for column in inspect(engine).get_columns('poker_games')}
        if 'was_hookah' not in columns:
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE poker_games ADD COLUMN was_hookah BOOLEAN NOT NULL DEFAULT 0'))
    return engine

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()

def generate_pie_chart_stats():
    session = get_session(init_db())
    
    stats = session.query(
        PokerGame.winner,
        func.sum(PokerGame.bank).label('total_bank')
    ).group_by(PokerGame.winner).all()
    
    if not stats:
        return None
    
    players = [stat.winner for stat in stats]
    banks = [float(stat.total_bank) for stat in stats]
    total = sum(banks)
    percentages = [bank/total*100 for bank in banks]
    
    plt.figure(figsize=(10, 8))
    
    explode = [0.1 if bank == max(banks) else 0 for bank in banks]
    
    # Красивые цвета
    colors = plt.cm.Pastel1(range(len(players)))
    
    wedges, texts, autotexts = plt.pie(
        banks,
        labels=players,
        autopct=lambda p: f'{p:.1f}%',
        startangle=140,
        colors=colors,
        explode=explode,
        shadow=True,
        textprops={'fontsize': 12}
    )
    
    for autotext in autotexts:
        autotext.set_color('black')
        autotext.set_fontsize(12)
    
    plt.title('Распределение выигранных банков между игроками', pad=20)
    
    legend_labels = [f'{p} - {b:.2f}' for p, b in zip(players, banks)]
    plt.legend(
        wedges,
        legend_labels,
        title="Игроки и их выигрыш за все время",
        loc="center left",
        bbox_to_anchor=(1, 0, 0.5, 1),
        fontsize=10
    )
    plt.setp(autotexts, size=12, weight="bold")  

    centre_circle = plt.Circle((0,0), 0.50, fc='white')
    fig = plt.gcf()
    fig.gca().add_artist(centre_circle)
    plt.text(0, 0, f"Всего разыграно:\n{total:.2f}", ha='center', va='center', fontsize=15)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf
