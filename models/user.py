import datetime
from enum import Enum
from .db import Base
from sqlalchemy import DECIMAL, Boolean, Column, DateTime, ForeignKey, Integer, String, Enum as SQLEnum
from sqlalchemy.orm import relationship


class Role(Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    GLOBAL_ADMIN = "global_admin"
    LOCAL_ADMIN = "local_admin"
    SMM = "smm"
    FINANCIER = "financier"
    SUPPORT = "support"
    USER = "user"


class History(Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, nullable=True)
    username = Column(String(64), unique=True)
    firtname = Column(String(64), nullable=True)
    lastname = Column(String(64), nullable=True)
    language_code = Column(String(8), nullable=True)
    phone_number = Column(String(32), unique=True)
    country = Column(String(32), nullable=True)
    email = Column(String(64), nullable=True)
    password = Column(String(128), nullable=True)
    role = Column(String(64), default=Role.USER.value)
    active = Column(Boolean, default=True)

    kyc = Column(Boolean, default=False)
    document = Column(String(256), nullable=True)

    referral_id = Column(Integer, ForeignKey('referral_links.id'), nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)


class Wallet(Base):
    __tablename__ = "wallet"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=True)
    address = Column(String(256), unique=True)
    private_key = Column(String(256), unique=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)


class Balance(Base):
    __tablename__ = "balance"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=True)
    currency_id = Column(Integer, ForeignKey('currencies.id', ondelete="CASCADE"), nullable=True)
    balance = Column(DECIMAL(20, 8), default=0)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    currency = relationship("Currency", uselist=False)


class BalanceChangeHistory(Base):
    class Status(Enum):
        PENDING = "pending"
        SUCCESS = "success"
        CANCELED = "canceled"
        INSUFFICIENT_FUNDS = "insufficient_funds"
        WEB3_ERROR = "web3_error"

    __tablename__ = "balance_change_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    balance_id = Column(Integer, ForeignKey('balance.id', ondelete='CASCADE'), nullable=True)
    currency_id = Column(Integer, ForeignKey('currencies.id', ondelete='CASCADE'), nullable=True)
    change_amount = Column(DECIMAL(20, 8), default=0)
    change_type = Column(String(64), nullable=False)
    previous_balance = Column(Integer, nullable=True)    
    status = Column(SQLEnum(Status), default=Status.PENDING)
    proof = Column(String(256), nullable=True)
    new_balance = Column(DECIMAL(20, 8), default=0)
    args = Column(String, nullable=True, default="{}")
    created_at = Column(DateTime, default=datetime.datetime.now)


class ReferralLink(Base):
    __tablename__ = "referral_links"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(256), nullable=False, unique=True)
    comment = Column(String(256), nullable=True)
    link = Column(String(256), nullable=False)
    generated_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    placement = Column(String(256), nullable=True, doc="placement of the link")
    user_count = Column(Integer, default=0)

    deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
