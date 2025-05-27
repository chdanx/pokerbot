from sqlalchemy import create_engine, Column, Integer, String, Date, Float, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import date

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
    name = Column(String, unique=True)

class PokerGame(Base):
    __tablename__ = 'poker_games'

    id = Column(Integer, primary_key=True)
    date = Column(Date, default=date.today())
    city = Column(String)
    players_count = Column(Integer)
    winner = Column(String)
    second_place = Column(String)
    rebuys = Column(Integer)
    bank = Column(Float)
    buyin = Column(Float)
    big_blind = Column(Integer)
    description = Column(String, nullable=True)

    # Связь с участниками
    players = relationship("Player", secondary=game_players_association, backref="poker_games")

def init_db():
    engine = create_engine('sqlite:///poker_games.db')
    Base.metadata.create_all(engine)
    return engine

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()
