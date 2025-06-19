from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    Enum as SqlEnum,
    DECIMAL,
    DateTime,
    ForeignKey, Boolean,
)
from sqlalchemy.orm import relationship, Mapped
import datetime
from enum import Enum
from src.utils.datastructure import MultiValueStrEnum
from .db import Base


class LimitType(Enum):
    SUM = "sum"
    NUMBER = "number"


class OperationType(Enum):
    ALL = "all"
    WITHDRAWAL = "withdraw"
    PURCHASE = "purchase"
    DEPOSIT = "deposit"


class Period(MultiValueStrEnum):
    label: Optional[datetime.timedelta]

    ALWAYS = "always", None
    SECOND = "second", datetime.timedelta(seconds=1)
    MINUTE = "minute", datetime.timedelta(minutes=1)
    HOUR = "hour", datetime.timedelta(hours=1)
    DAY = "day", datetime.timedelta(days=1)
    WEEK = "week", datetime.timedelta(weeks=1)
    MONTH = "month", datetime.timedelta(days=30)
    YEAR = "year", datetime.timedelta(days=365)


class LimitStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class RiskLevel(Enum):
    CRITICAL = "critical"  # Hard Limit
    NORMAL = "normal"  # Lockout Limit
    ESCALATE = "escalate"  # TBD
    SOFT = "soft"  # Soft Limit


class Limit(Base):
    __tablename__ = "limits"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    type: Mapped[LimitType] = Column(SqlEnum(LimitType), nullable=False, doc="Type of limit")
    value: Mapped[float] = Column(DECIMAL(10, 2), nullable=False, doc="Limit value")
    currency_id: Mapped[int] = Column(Integer, ForeignKey('currencies.id'), nullable=False, doc="Currency ID")
    operation_type: Mapped[OperationType] = Column(SqlEnum(OperationType), nullable=False, doc="Type of operations")
    period: Mapped[Period] = Column(SqlEnum(Period), nullable=False, doc="Limit validity period")
    kyc: Mapped[bool] = Column(Boolean, default=False)
    status: Mapped[LimitStatus] = Column(SqlEnum(LimitStatus), nullable=False, default=LimitStatus.ACTIVE, doc="Limit status")
    risk: Mapped[RiskLevel] = Column(SqlEnum(RiskLevel), nullable=True, doc="Criticality indicator")
    created_at: Mapped[datetime.datetime] = Column(DateTime, default=datetime.datetime.now, doc="Date the limit was added")
    updated_at: Mapped[datetime.datetime] = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now,
        doc="Date of the last limit update"
    )
    last_edited: Mapped[int] = Column(Integer, ForeignKey('users.id'), nullable=True, doc="ID of the user who made the last changes")
    is_deleted: Mapped[bool] = Column(Boolean, default=False, doc="Is the limit deleted?")

    last_editor = relationship("User", uselist=False, doc="User who made the last changes")
