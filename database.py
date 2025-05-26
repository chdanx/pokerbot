from sqlalchemy import create_engine, Column, Integer, String, Date, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import date

Base = declarative_base()

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

def init_db():
    engine = create_engine('sqlite:///poker_games.db')
    Base.metadata.create_all(engine)
    return engine

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()