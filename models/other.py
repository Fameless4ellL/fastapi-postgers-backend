import datetime
from enum import Enum
from .db import Base
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Enum as SqlEnum,
    ARRAY,
    DECIMAL,
    Boolean
)
from sqlalchemy.orm import relationship


class GameType(Enum):
    GLOBAL = "Global"
    LOCAL = "Local"


class GameView(Enum):
    MONETARY = "monetary"
    MATERIAL = "material"


class GameStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Currency(Base):
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(8), unique=True, nullable=False, doc="e.g., USDT, TON")
    name = Column(String(64), nullable=False, doc="e.g., Tether, TON Crystal")

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    game_type = Column(SqlEnum(GameType), nullable=False)
    limit_by_ticket = Column(Integer, default=9)
    max_limit_grid = Column(Integer, default=90)
    price = Column(DECIMAL(10, 2), nullable=False, default=1)
    description = Column(String(500), nullable=True, doc="Description of the game")
    max_win_amount = Column(DECIMAL(9, 2), nullable=True)
    prize = Column(DECIMAL(9, 2), nullable=True)
    country = Column(String(32), nullable=True)
    min_ticket_count = Column(Integer, default=1, doc="Minimum number of tickets per user")
    as_default = Column(Boolean, default=False, doc="Is the game default")
    
    scheduled_datetime = Column(DateTime, default=datetime.datetime.utcnow, doc="The date and time when the game instance will be held")
    timezone = Column(String(50), default="UTC", doc="The timezone of the game instance in UTC format")
    
    repeat = Column(Boolean, default=False, doc="Indicates if the game instance is repeated")
    repeat_days = Column(ARRAY(Integer), nullable=True, doc="The days of the week when the game instance is repeated, required if repeat is True")

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    game_instances = relationship("GameInstance", back_populates="game", uselist=False)


class GameInstance(Base):
    __tablename__ = "game_instances"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey('games.id'), nullable=False)
    status = Column(SqlEnum(GameStatus), default=GameStatus.PENDING)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    game = relationship("Game", back_populates="game_instances", uselist=False)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    game_instance_id = Column(Integer, ForeignKey('game_instances.id'), nullable=False)
    numbers = Column(ARRAY(Integer), nullable=False)
    won = Column(Boolean, default=False)
    amount = Column(DECIMAL(9, 2), default=0)
    demo = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
