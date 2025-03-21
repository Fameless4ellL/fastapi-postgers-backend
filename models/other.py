import datetime
from enum import Enum
from .db import Base
from sqlalchemy import (
    JSON,
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
    MONETARY = "Monetary"
    MATERIAL = "Clothing"


class GameStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DELETED = "deleted"


class TicketStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class JackpotStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Network(Base):
    __tablename__ = "networks"

    id = Column(Integer, primary_key=True, index=True)
    chain_id = Column(Integer, nullable=False, doc="The chain ID of the network")
    name = Column(String(100), nullable=False)
    symbol = Column(String(8), unique=True, nullable=False, doc="e.g., ETH, BTC")
    rpc_url = Column(String(255), nullable=False, doc="The RPC URL of the network")
    explorer_url = Column(String(255), nullable=False, doc="The explorer URL of the network")

    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)


class Currency(Base):
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(8), unique=True, nullable=False, doc="e.g., USDT, TON")
    name = Column(String(64), nullable=False, doc="e.g., Tether, TON Crystal")
    network_id = Column(Integer, ForeignKey('networks.id'), nullable=True, doc="The network ID of the currency")
    address = Column(String(255), nullable=False, doc="The address of the contract")
    decimals = Column(Integer, nullable=True, default=18, doc="The number of decimals of the currency")
    conversion_rate = Column(DECIMAL(10, 2), nullable=False, default=1, doc="The conversion rate to the base currency")

    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    network = relationship("Network", uselist=False)


class Jackpot(Base):
    __tablename__ = "jackpots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    _type = Column(SqlEnum(JackpotType), default=JackpotType.GLOBAL)
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=True)
    percentage = Column(DECIMAL(5, 2), default=10, doc="Percentage of deductions from daily money games")
    image = Column(String(255), nullable=True, default="default_jackpot.png", doc="The image of the instance")
    country = Column(String(32), nullable=True)

    scheduled_datetime = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the game instance will be held")
    tzone = Column(Integer, default=1, doc="The timezone of the game instance in UTC format")
    repeat = Column(Boolean, default=False, doc="Indicates if the instance is repeated")
    repeat_days = Column(
        ARRAY(Integer),
        default=[0, 1, 2, 3, 4, 5, 6],
        doc="The days of the week when the instance is repeated, required if repeat is True"
    )

    amount = Column(DECIMAL(9, 2), nullable=True, default=0)

    image = Column(String(255), nullable=True, default="default_image.png", doc="The image of the game instance")
    status = Column(SqlEnum(GameStatus), default=GameStatus.PENDING)

    numbers = Column(ARRAY(Integer), nullable=True)
    fund_start = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the fundraising will be held")
    fund_end = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the fundraising will be ended")

    event_start = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the game instance will be started")
    event_end = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the game instance will be ended")
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    currency = relationship("Currency", uselist=False)
    tickets = relationship("Ticket", back_populates="jackpot", uselist=True)


class InstaBingo(Base):
    __tablename__ = "instabingos"

    id = Column(Integer, primary_key=True, index=True)
    country = Column(String(32))
    price = Column(DECIMAL(10, 2), nullable=False, default=1)
    winnings = Column(JSON, nullable=True)
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=True)

    deleted = Column(Boolean, default=False, doc="Indicates if the instance is deleted")
    created_at = Column(DateTime, default=datetime.datetime.now)


class Number(Base):
    __tablename__ = "numbers"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(Integer, nullable=False)
    ticket_id = Column(Integer, ForeignKey('tickets.id'), nullable=True)
    start_date = Column(DateTime, default=datetime.datetime.now)
    end_date = Column(DateTime, default=datetime.datetime.now)
    created_at = Column(DateTime, default=datetime.datetime.now)


class Game(Base):

    id = Column(Integer, primary_key=True, index=True)
    __tablename__ = "games"

    game_type = Column(SqlEnum(GameType), nullable=False)
    name = Column(String(100), nullable=False)
    kind = Column(SqlEnum(GameView), default=GameView.MONETARY, doc="The type of the game", nullable=True)
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=True)
    limit_by_ticket = Column(Integer, default=9)
    max_limit_grid = Column(Integer, default=90)
    price = Column(DECIMAL(10, 2), nullable=False, default=1)
    description = Column(String(500), nullable=True, doc="Description of the game")
    max_win_amount = Column(DECIMAL(9, 2), nullable=True, default=8)
    prize = Column(String(256), nullable=True, default="1000", doc="The prize of the game instance")
    country = Column(String(32), nullable=True)
    min_ticket_count = Column(Integer, default=1, doc="Minimum number of tickets per user")

    numbers = Column(ARRAY(Integer), nullable=True)

    image = Column(String(255), nullable=True, default="default_image.png", doc="The image of the game instance")
    status = Column(SqlEnum(GameStatus), default=GameStatus.PENDING)

    scheduled_datetime = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the game instance will be held")
    zone = Column(Integer, default=1, doc="The timezone of the game instance in UTC format")

    repeat = Column(Boolean, default=False, doc="Indicates if the game instance is repeated")
    repeat_days = Column(
        ARRAY(Integer),
        default=[0, 1, 2, 3, 4, 5, 6],
        doc="The days of the week when the game instance is repeated, required if repeat is True"
    )

    event_start = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the game instance will be started")
    event_end = Column(DateTime, default=datetime.datetime.now, doc="The date and time when the game instance will be ended")
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    currency = relationship("Currency", uselist=False)
    tickets = relationship("Ticket", back_populates="game", uselist=True)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    game_id = Column(Integer, ForeignKey('games.id'), nullable=True)
    instabingo_id = Column(Integer, ForeignKey('instabingos.id'), nullable=True)
    jackpot_id = Column(Integer, ForeignKey('jackpots.id'), nullable=True)
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=True)
    numbers = Column(ARRAY(Integer), nullable=False)
    won = Column(Boolean, default=False)
    amount = Column(DECIMAL(9, 2), default=0)
    status = Column(SqlEnum(TicketStatus), default=TicketStatus.PENDING)
    demo = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    currency = relationship("Currency", uselist=False)
    jackpot = relationship("Jackpot", back_populates="tickets", uselist=False)
    game = relationship("Game", back_populates="tickets", uselist=False)
