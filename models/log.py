import datetime
import decimal
from enum import Enum
from typing import Union

from sqlalchemy.orm import Mapped

from .db import LogsBase
from sqlalchemy import (
    DECIMAL,
    Column,
    DateTime,
    Integer,
    String,
    JSON,
    Enum as EnumColumn,
    ForeignKey
)


class Action(Enum):
    LOGIN = 'login'
    LOGOUT = 'logout'
    REGISTER = 'register'
    DEPOSIT = 'deposit'
    WITHDRAW = 'withdraw'
    TRANSACTION = 'transaction'
    UPDATE = 'update'
    OTHER = 'other'
    ADMIN_LOGIN = 'admin_login'
    ADMIN_LOGOUT = 'admin_logout'
    ADMIN_CREATE = 'admin_create'
    ADMIN_UPDATE = 'admin_update'
    ADMIN_DELETE = 'admin_delete'


class RequestLog(LogsBase):
    __tablename__ = 'request_logs'

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    method: Mapped[str] = Column(String, index=True)
    headers: Mapped[dict[str, str]] = Column(JSON)
    body: Mapped[dict[str, str]] = Column(JSON)
    response: Mapped[dict[str, str]] = Column(JSON)
    url: Mapped[str] = Column(String, index=True)
    status_code: Mapped[int] = Column(Integer)
    timestamp: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    response_time: Mapped[decimal.Decimal] = Column(DECIMAL(10, 2))


class TransactionLog(LogsBase):
    __tablename__ = 'transaction_logs'

    class Status(Enum):
        PENDING = 'pending'
        SUCCESS = 'success'
        FAILED = 'failed'

    class TransactionAction(Enum):
        DEPOSIT = 'deposit'
        WITHDRAW = 'withdraw'
        TRANSFER = 'transfer'

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    transaction_id: Mapped[str] = Column(String, index=True)
    user_id: Mapped[int] = Column(Integer, index=True)
    action: Mapped[TransactionAction] = Column(EnumColumn(TransactionAction), index=True)
    status: Mapped[Status] = Column(EnumColumn(Status), index=True)
    arguments: Mapped[dict[str, str]] = Column(JSON)
    timestamp: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)


class UserActionLog(LogsBase):
    __tablename__ = 'user_action_logs'

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = Column(Integer, index=True)
    action: Mapped[Action] = Column(EnumColumn(Action), index=True)
    request_id: Mapped[int] = Column(Integer, ForeignKey('request_logs.id', ondelete="CASCADE"))
    country: Mapped[Union[str, None]] = Column(String(32), index=True)
    timestamp: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)


class Metric(LogsBase):
    __tablename__ = 'metrics'

    class MetricType(Enum):
        TOTAL_SOLD_TICKETS = "total_sold_tickets"
        ARPU = "arpu"
        ARPPU = "arppu"
        LTV = "ltv"
        GGR = "ggr"
        FTD = "ftd"
        CPA = "cpa"
        DAU = "dau"
        AVG_SESSION_TIME = "session_time"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    currency_id: Mapped[Union[int, None]] = Column(Integer, index=True)
    country: Mapped[Union[str, None]] = Column(String(32), index=True)
    name: Mapped[str] = Column(EnumColumn(MetricType))
    value: Mapped[decimal.Decimal] = Column(DECIMAL(10, 2))
    created: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
