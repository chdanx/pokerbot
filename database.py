from sqlalchemy import create_engine, Column, Integer, String, Date, Float, ForeignKey, Table, func
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