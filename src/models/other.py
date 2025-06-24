import datetime
import decimal
from enum import Enum

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
from sqlalchemy.orm import relationship, Mapped

from . import MinioStorage, FileType
from .db import Base
from .utils import generate_unique_ticket_number


class GameType(Enum):
    GLOBAL = "Global"
    LOCAL = "Local"


class JackpotType(Enum):
    GLOBAL = "Global"
    LOCAL = "Local"


class RepeatType(Enum):
    NONE = "none"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class GameView(Enum):
    MONETARY = "Monetary"
    MATERIAL = "Clothing"


class GameStatus(Enum):
    NEW = "new"
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

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    chain_id: Mapped[int] = Column(Integer, nullable=False, doc="The chain ID of the network")
    name: Mapped[str] = Column(String(100), nullable=False)
    symbol: Mapped[str] = Column(String(8), unique=True, nullable=False, doc="e.g., ETH, BTC")
    rpc_url: Mapped[str] = Column(String(255), nullable=False, doc="The RPC URL of the network")
    explorer_url: Mapped[str] = Column(String(255), nullable=False, doc="The explorer URL of the network")

    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)


class Currency(Base):
    __tablename__ = "currencies"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    code: Mapped[int] = Column(String(8), unique=True, nullable=False, doc="e.g., USDT, TON")
    name: Mapped[str] = Column(String(64), nullable=False, doc="e.g., Tether, TON Crystal")
    network_id: Mapped[int] = Column(Integer, ForeignKey('networks.id'), nullable=True, doc="The network ID of the currency")
    address: Mapped[str] = Column(String(255), nullable=False, doc="The address of the contract")
    decimals: Mapped[int] = Column(Integer, nullable=True, default=18, doc="The number of decimals of the currency")
    conversion_rate: Mapped[decimal.Decimal] = Column(DECIMAL(10, 2), nullable=False, default=1, doc="The conversion rate to the base currency")

    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    network = relationship("Network", uselist=False)


class Jackpot(Base):
    __tablename__ = "jackpots"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    name: Mapped[str] = Column(String(100), nullable=False)
    _type: Mapped[JackpotType] = Column(SqlEnum(JackpotType), default=JackpotType.GLOBAL)
    currency_id: Mapped[int] = Column(Integer, ForeignKey('currencies.id'), nullable=True)
    percentage: Mapped[decimal.Decimal] = Column(DECIMAL(5, 2), default=10, doc="Percentage of deductions from daily money games")
    image: Mapped[str] = Column(
        FileType(storage=MinioStorage(bucket="games", path="jackpot", public=True)),
        nullable=True,
        doc="The image of the instance"
    )
    country: Mapped[str] = Column(String(32), nullable=True)

    scheduled_datetime: Mapped[datetime.datetime] = Column(
        DateTime(timezone=True),
        default=datetime.datetime.now,
        doc="The date and time when the game instance will be held"
    )
    tzone: Mapped[int] = Column(Integer, default=1, doc="The timezone of the game instance in UTC format")
    repeat_type: Mapped[RepeatType] = Column(SqlEnum(RepeatType), default=RepeatType.NONE, doc="The type of repetition (weekly, monthly, yearly)")

    amount: Mapped[decimal.Decimal] = Column(DECIMAL(9, 2), nullable=True, default=0)
    status: Mapped[GameStatus] = Column(SqlEnum(GameStatus), default=GameStatus.NEW)

    numbers: Mapped[list[int]] = Column(ARRAY(Integer), nullable=True)
    fund_start: Mapped[datetime.datetime] = Column(
        DateTime(timezone=True),
        default=datetime.datetime.now,
        doc="The date and time when the fundraising will be held"
    )
    fund_end: Mapped[datetime.datetime] = Column(
        DateTime(timezone=True),
        default=datetime.datetime.now,
        doc="The date and time when the fundraising will be ended"
    )

    event_start: Mapped[datetime.datetime] = Column(
        DateTime(timezone=True),
        default=datetime.datetime.now,
        doc="The date and time when the game instance will be started"
    )
    event_end: Mapped[datetime.datetime] = Column(
        DateTime(timezone=True),
        default=datetime.datetime.now,
        doc="The date and time when the game instance will be ended"
    )
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    currency = relationship("Currency", uselist=False)
    tickets = relationship("Ticket", back_populates="jackpot", uselist=True)

    def next_scheduled_date(self):
        if self.repeat_type == RepeatType.WEEKLY:
            return self.scheduled_datetime + datetime.timedelta(weeks=1)
        elif self.repeat_type == RepeatType.MONTHLY:
            return self.scheduled_datetime + datetime.timedelta(days=30)
        elif self.repeat_type == RepeatType.YEARLY:
            return self.scheduled_datetime + datetime.timedelta(days=365)
        return None


class InstaBingo(Base):
    __tablename__ = "instabingos"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    country: Mapped[str] = Column(String(32), nullable=True)
    price: Mapped[decimal.Decimal] = Column(DECIMAL(10, 2), nullable=False, default=1)
    winnings: Mapped[dict] = Column(JSON, nullable=True)
    currency_id: Mapped[int] = Column(Integer, ForeignKey('currencies.id'), nullable=True)

    deleted: Mapped[bool] = Column(Boolean, default=False, doc="Indicates if the instance is deleted")
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)

    currency = relationship("Currency", uselist=False)


class Number(Base):
    __tablename__ = "numbers"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    number: Mapped[int] = Column(Integer, nullable=False)
    ticket_id: Mapped[int] = Column(Integer, ForeignKey('tickets.id'), nullable=True)
    start_date: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    end_date: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    game_type: Mapped[GameType] = Column(SqlEnum(GameType), nullable=False)
    name: Mapped[str] = Column(String(100), nullable=False)
    kind: Mapped[GameView] = Column(SqlEnum(GameView), default=GameView.MONETARY, doc="The type of the game", nullable=True)
    currency_id: Mapped[int] = Column(Integer, ForeignKey('currencies.id'), nullable=True)
    limit_by_ticket: Mapped[int] = Column(Integer, default=9)
    max_limit_grid: Mapped[int] = Column(Integer, default=90)
    price: Mapped[decimal.Decimal] = Column(DECIMAL(10, 2), nullable=False, default=1)
    description: Mapped[str] = Column(String(500), nullable=True, doc="Description of the game")
    max_win_amount: Mapped[decimal.Decimal] = Column(DECIMAL(9, 2), nullable=True, default=8)
    prize: Mapped[str] = Column(String(256), nullable=True, default="0", doc="The prize of the game instance")
    country: Mapped[str] = Column(String(32), nullable=True)
    min_ticket_count: Mapped[int] = Column(Integer, default=1, doc="Minimum number of tickets per user")

    numbers: Mapped[list[int]] = Column(ARRAY(Integer), nullable=True)

    image: Mapped[str] = Column(
        FileType(storage=MinioStorage(bucket="games", path="game", public=True)),
        nullable=True,
        doc="The image of the game instance"
    )
    status: Mapped[GameStatus] = Column(SqlEnum(GameStatus), default=GameStatus.PENDING)

    scheduled_datetime: Mapped[datetime.datetime] = Column(
        DateTime(timezone=True),
        default=datetime.datetime.now,
        doc="The date and time when the game instance will be held"
    )
    zone: Mapped[int] = Column(Integer, default=1, doc="The timezone of the game instance in UTC format")

    repeat: Mapped[bool] = Column(Boolean, default=False, doc="Indicates if the game instance is repeated")
    repeat_days: Mapped[list[int]] = Column(
        ARRAY(Integer),
        default=[0, 1, 2, 3, 4, 5, 6],
        doc="The days of the week when the game instance is repeated, required if repeat is True"
    )

    event_start: Mapped[datetime.datetime] = Column(
        DateTime(timezone=True),
        default=datetime.datetime.now,
        doc="The date and time when the game instance will be started"
    )
    event_end: Mapped[datetime.datetime] = Column(
        DateTime(timezone=True),
        default=datetime.datetime.now,
        doc="The date and time when the game instance will be ended"
    )
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    currency = relationship("Currency", uselist=False)
    tickets = relationship("Ticket", back_populates="game", uselist=True)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = Column(Integer, ForeignKey('users.id'), nullable=False)
    game_id: Mapped[int] = Column(Integer, ForeignKey('games.id'), nullable=True)
    instabingo_id: Mapped[int] = Column(Integer, ForeignKey('instabingos.id'), nullable=True)
    jackpot_id: Mapped[int] = Column(Integer, ForeignKey('jackpots.id'), nullable=True)
    currency_id: Mapped[int] = Column(Integer, ForeignKey('currencies.id'), nullable=True)
    number: Mapped[str] = Column(
        String(15),
        unique=True,
        default=generate_unique_ticket_number,
        doc="The unique ticket number"
    )
    numbers: Mapped[list[int]] = Column(ARRAY(Integer), nullable=False)
    won: Mapped[bool] = Column(Boolean, default=False)
    price: Mapped[decimal.Decimal] = Column(DECIMAL(10, 2), nullable=False, default=1, doc="static price at the time of creation")
    amount: Mapped[decimal.Decimal] = Column(DECIMAL(9, 2), default=0)
    status: Mapped[TicketStatus] = Column(SqlEnum(TicketStatus), default=TicketStatus.PENDING)
    demo: Mapped[bool] = Column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    currency = relationship("Currency", uselist=False)
    jackpot = relationship("Jackpot", back_populates="tickets", uselist=False)
    game = relationship("Game", back_populates="tickets", uselist=False)

