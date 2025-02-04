from pydantic import BaseModel, Field
from typing import Optional


class User(BaseModel):
    username: str
    id: int
    phone_number: Optional[str] = None
    country: Optional[str] = "EN"


class Users(BaseModel):
    users: list[User] = []
    count: int = 0


class Ticket(BaseModel):
    purchased: int = 0


class Winnings(BaseModel):
    winnings: int = 0


class UserInfo(User):
    telegram_id: Optional[int]
    language_code: Optional[str]
    email: Optional[str]
    role: str
    created_at: str
    updated_at: str
    tickets: Ticket = Field(default=Ticket())
    winnings: Winnings = Field(default=Winnings())
