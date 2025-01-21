from enum import Enum
from .db import Base
from sqlalchemy import Column, Integer, String


class Role(Enum):
    ADMIN = "admin"
    USER = "user"


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
