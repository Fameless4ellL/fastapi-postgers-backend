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
    Boolean,
)
from sqlalchemy.orm import relationship


class GameType(Enum):
    GLOBAL = "Global"
    LOCAL = "Local"


class JackpotType(Enum):
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


class JackpotStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Currency(Base):
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(8), unique=True, nullable=False, doc="e.g., USDT, TON")
    name = Column(String(64), nullable=False, doc="e.g., Tether, TON Crystal")
    conversion_rate = Column(DECIMAL(10, 2), nullable=False, default=1, doc="The conversion rate to the base currency")

    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)


class Jackpot(Base):
    __tablename__ = "jackpots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    _type = Column(SqlEnum(JackpotType), nullable=False)
    percentage = Column(DECIMAL(5, 2), default=10, doc="Percentage of deductions from daily money games")
    image = Column(String(255), nullable=True, default="default_image.png", doc="The image of the instance")
    country = Column(String(32), nullable=True)

    scheduled_datetime = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the game instance will be held")
    tzone = Column(Integer, default=1, doc="The timezone of the game instance in UTC format")
    repeat = Column(Boolean, default=False, doc="Indicates if the instance is repeated")
    repeat_days = Column(
        ARRAY(Integer),
        default=[0, 1, 2, 3, 4, 5, 6],
        doc="The days of the week when the instance is repeated, required if repeat is True"
    )

    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    jackpot_instances = relationship("JackpotInstance", back_populates="jackpot", uselist=False)


class JackpotInstance(Base):
    __tablename__ = "jackpot_instances"

    id = Column(Integer, primary_key=True, index=True)
    jackpot_id = Column(Integer, ForeignKey('jackpots.id'), nullable=False)
    status = Column(SqlEnum(JackpotStatus), default=JackpotStatus.PENDING)
    scheduled_datetime = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the game instance will be held")
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    jackpot = relationship("Jackpot", back_populates="jackpot_instances", uselist=False)


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    game_type = Column(SqlEnum(GameType), nullable=False)
    limit_by_ticket = Column(Integer, default=9)
    max_limit_grid = Column(Integer, default=90)
    price = Column(DECIMAL(10, 2), nullable=False, default=1)
    description = Column(String(500), nullable=True, doc="Description of the game")
    max_win_amount = Column(DECIMAL(9, 2), nullable=True, default=8)
    prize = Column(DECIMAL(9, 2), nullable=True, default=1000)
    country = Column(String(32), nullable=True)
    min_ticket_count = Column(Integer, default=1, doc="Minimum number of tickets per user")

    scheduled_datetime = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the game instance will be held")
    zone = Column(Integer, default=1, doc="The timezone of the game instance in UTC format")

    repeat = Column(Boolean, default=False, doc="Indicates if the game instance is repeated")
    repeat_days = Column(
        ARRAY(Integer),
        default=[0, 1, 2, 3, 4, 5, 6],
        doc="The days of the week when the game instance is repeated, required if repeat is True"
    )

    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    game_instances = relationship("GameInstance", back_populates="game", uselist=False)


class GameInstance(Base):
    __tablename__ = "game_instances"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey('games.id'), nullable=False)
    status = Column(SqlEnum(GameStatus), default=GameStatus.PENDING)
    scheduled_datetime = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the game instance will be held")
    image = Column(String(255), nullable=True, default="default_image.png", doc="The image of the game instance")
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    game = relationship("Game", back_populates="game_instances", uselist=False)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    game_instance_id = Column(Integer, ForeignKey('game_instances.id'), nullable=False)
    jackpot_id = Column(Integer, ForeignKey('jackpots.id'), nullable=True)
    numbers = Column(ARRAY(Integer), nullable=False)
    won = Column(Boolean, default=False)
    amount = Column(DECIMAL(9, 2), default=0)
    demo = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
