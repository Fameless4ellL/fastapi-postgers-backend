from enum import Enum
from .db import Base
from sqlalchemy import Column, Integer, String


class Role(Enum):
    ADMIN = "admin"
    USER = "user"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64))
    email = Column(String(64))
    role = Column(String(64), default=Role.USER.value)
