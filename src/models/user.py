import datetime
import decimal
import os
from enum import Enum
from typing import Union

from sqlalchemy import DECIMAL, Boolean, Column, DateTime, ForeignKey, Integer, String, Enum as SQLEnum
from sqlalchemy.orm import relationship, Mapped

from src.globals import TotpFactory
from .custom_types import FileType
from .db import Base
from .storage import MinioStorage


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

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    telegram: Mapped[str] = Column(String(64))
    telegram_id: Mapped[Union[int, None]] = Column(Integer, unique=True, nullable=True)
    username: Mapped[Union[str, None]] = Column(String(64), unique=True, nullable=True)
    firstname: Mapped[Union[str, None]] = Column(String(64), nullable=True)
    patronomic: Mapped[Union[str, None]] = Column(String(64), nullable=True)
    lastname: Mapped[Union[str, None]] = Column(String(64), nullable=True)
    language_code: Mapped[Union[str, None]] = Column(String(8), nullable=True)
    phone_number: Mapped[str] = Column(String(32), unique=True)
    country: Mapped[Union[str, None]] = Column(String(32), nullable=True)
    email: Mapped[Union[str, None]] = Column(String(64), nullable=True)
    password: Mapped[Union[str, None]] = Column(String(128), nullable=True)
    role: Mapped[str] = Column(String(64), default=Role.USER.value)
    active: Mapped[bool] = Column(Boolean, default=True)

    kyc: Mapped[bool] = Column(Boolean, default=False)

    _avatar_v1: Mapped[FileType] = Column(FileType(storage=MinioStorage(bucket="users", path="avatars")))

    totp: Mapped[str] = Column(String(256), nullable=True, default=TotpFactory.new().to_json())
    verified: Mapped[bool] = Column(Boolean, default=False)

    referral_id: Mapped[Union[int, None]] = Column(Integer, ForeignKey('referral_links.id'), nullable=True)

    is_blocked: Mapped[bool] = Column(Boolean, default=False)

    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    last_session: Mapped[Union[datetime.datetime, None]] = Column(DateTime, nullable=True)
    updated_at: Mapped[datetime.datetime] = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now
    )

    def __str__(self):
        return f"{self.firstname} {self.lastname} ({self.username})"

    @property
    def avatar_v1(self):
        return self._avatar_v1

    @avatar_v1.setter
    def avatar_v1(self, value):
        if self._avatar_v1 and os.path.exists(self._avatar_v1.path):
            os.remove(self._avatar_v1.path)

        # Сохранение нового файла
        value.filename = f"{self.id}/{value.filename}"
        self._avatar_v1 = value


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    file: Mapped[FileType] = Column(FileType(storage=MinioStorage(bucket="users", path="kyc")))
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now
    )


class Kyc(Base):
    __tablename__ = "kyc"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    country: Mapped[str] = Column(String(32))


class Wallet(Base):
    __tablename__ = "wallet"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=True)
    address: Mapped[str] = Column(String(256), unique=True)
    private_key: Mapped[str] = Column(String(256), unique=True)
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now
    )


class Balance(Base):
    __tablename__ = "balance"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=True)
    currency_id: Mapped[int] = Column(Integer, ForeignKey('currencies.id', ondelete="CASCADE"), nullable=True)
    balance: Mapped[decimal.Decimal] = Column(DECIMAL(20, 8), default=0)
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)
    updated_at: Mapped[datetime.datetime] = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now
    )

    currency = relationship("Currency", uselist=False)


class BalanceChangeHistory(Base):
    class Status(Enum):
        PENDING = "pending"
        SUCCESS = "success"
        BLOCKED = "blocked"
        CANCELED = "canceled"
        INSUFFICIENT_FUNDS = "insufficient_funds"
        WEB3_ERROR = "web3_error"

    class GameInstanceType(Enum):
        JACKPOT = "Jackpot"
        INSTABINGO = "InstaBingo"
        GAME = "Game"

    __tablename__ = "balance_change_history"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    balance_id: Mapped[int] = Column(Integer, ForeignKey('balance.id', ondelete='CASCADE'), nullable=True)
    currency_id: Mapped[int] = Column(Integer, ForeignKey('currencies.id', ondelete='CASCADE'), nullable=True)
    game_id: Mapped[int] = Column(Integer, nullable=True, doc="Game ID")
    game_type: Mapped[GameInstanceType] = Column(SQLEnum(GameInstanceType), nullable=True, doc="Type of the related game")
    change_amount: Mapped[decimal.Decimal] = Column(DECIMAL(20, 8), default=0)
    change_type: Mapped[str] = Column(String(64), nullable=False)
    previous_balance: Mapped[int] = Column(Integer, nullable=True)
    status: Mapped[Status] = Column(SQLEnum(Status), default=Status.PENDING)
    count: Mapped[int] = Column(Integer, nullable=True, default=1)
    proof: Mapped[str] = Column(String(256), nullable=True)
    new_balance: Mapped[decimal.Decimal] = Column(DECIMAL(20, 8), default=0)
    args: Mapped[str] = Column(String, nullable=True, default="{}")
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)


class ReferralLink(Base):
    __tablename__ = "referral_links"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    name: Mapped[str] = Column(String(256), nullable=False)
    comment: Mapped[str] = Column(String(256), nullable=True)
    link: Mapped[str] = Column(String(256), nullable=False, index=True)
    generated_by: Mapped[int] = Column(Integer, ForeignKey('users.id'), nullable=False)
    user_count: Mapped[int] = Column(Integer, default=0)

    deleted: Mapped[bool] = Column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    head: Mapped[str] = Column(String(256), nullable=False)
    body: Mapped[str] = Column(String(256), nullable=False)
    args: Mapped[dict[str, str]] = Column(String, nullable=True, default="{}")
    read: Mapped[bool] = Column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now)