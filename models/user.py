import datetime
from enum import Enum
from .db import Base
from sqlalchemy.orm import relationship
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
    telegram_id = Column(Integer, unique=True)
    first_name = Column(String(64))
    last_name = Column(String(64))
    language_code = Column(String(8))
    phone_number = Column(String(16), nullable=True)
    email = Column(String(64), nullable=True)
    role = Column(String(64), default=Role.USER.value)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    balance = relationship("Balance", back_populates="user", uselist=False)


class Balance(Base):
    __tablename__ = "balance"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="SET NULL"), nullable=True)
    balance = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="balance")


class BalanceChangeHistory(Base):
    __tablename__ = "balance_change_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    change_amount = Column(Integer, nullable=False)
    change_type = Column(String(64), nullable=False)
    previous_balance = Column(Integer, nullable=False)
    new_balance = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="balance_change_history")
