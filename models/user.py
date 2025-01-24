import datetime
from enum import Enum
from .db import Base
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String


class Role(Enum):
    ADMIN = "admin"
    USER = "user"


class History(Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, nullable=True)
    username = Column(String(64), unique=True)
    language_code = Column(String(8), nullable=True)
    phone_number = Column(String(16), unique=True)
    country = Column(String(32), nullable=True)
    email = Column(String(64), nullable=True)
    password = Column(String(128))
    role = Column(String(64), default=Role.USER.value)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Balance(Base):
    __tablename__ = "balance"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=True)
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    balance = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class BalanceChangeHistory(Base):
    __tablename__ = "balance_change_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    balance_id = Column(Integer, ForeignKey('balance.id', ondelete='CASCADE'), nullable=True)
    change_amount = Column(Integer, nullable=False)
    change_type = Column(String(64), nullable=False)
    previous_balance = Column(Integer, nullable=False)
    new_balance = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
