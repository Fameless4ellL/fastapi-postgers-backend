import datetime
from enum import Enum
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
    ADMIN_LOGIN = 'admin_login'
    ADMIN_LOGOUT = 'admin_logout'
    ADMIN_CREATE = 'admin_create'
    ADMIN_UPDATE = 'admin_update'
    ADMIN_DELETE = 'admin_delete'


class RequestLog(LogsBase):
    __tablename__ = 'request_logs'

    id = Column(Integer, primary_key=True, index=True)
    method = Column(String, index=True)
    headers = Column(JSON)
    body = Column(JSON)
    response = Column(JSON)
    url = Column(String, index=True)
    status_code = Column(Integer)
    timestamp = Column(DateTime, default=datetime.datetime.now)
    response_time = Column(DECIMAL(10, 2))


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

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, index=True)
    user_id = Column(Integer, index=True)
    action = Column(EnumColumn(TransactionAction), index=True)
    status = Column(EnumColumn(Status), index=True)
    arguments = Column(JSON)
    timestamp = Column(DateTime, default=datetime.datetime.now)


class UserActionLog(LogsBase):
    __tablename__ = 'user_action_logs'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    action = Column(EnumColumn(Action), index=True)
    request_id = Column(Integer, ForeignKey('request_logs.id', ondelete="CASCADE"))
    timestamp = Column(DateTime, default=datetime.datetime.now)
