from pydantic import BaseModel, Field, SecretStr, ConfigDict
from typing import Optional
from datetime import datetime

from models.other import GameType


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
    balance: int
    tickets: Ticket = Field(default=Ticket())
    winnings: Winnings = Field(default=Winnings())


class UserGame(BaseModel):
    game_instance_id: int
    game_name: str
    scheduled_datetime: Optional[str] = None
    tickets_purchased: int
    amount: float = 0.0


class UserGames(BaseModel):
    games: list[UserGame] = []
    count: int = 0


class UserJackpot(BaseModel):
    jackpot_instance_id: int
    game_name: str
    scheduled_datetime: Optional[str] = None
    tickets_purchased: int


class UserJackpots(BaseModel):
    jackpots: list[UserJackpot] = []
    count: int = 0


class UserTickets(BaseModel):
    id: int
    game_name: str
    numbers: list[int]
    date_and_time: str
    won: bool
    amount: float


class Admin(User):
    email: Optional[str]
    role: str


class Admins(BaseModel):
    admins: list[Admin] = []
    count: int = 0


class AdminLogin(BaseModel):
    login: str
    password: SecretStr = Field(..., min_length=3, max_length=64, description="Password")


class ResetPassword(BaseModel):
    email: str
    password: SecretStr
    code: str = Field(..., min_length=6, max_length=6, description="email code")


class NetworkBase(BaseModel):
    chain_id: int
    name: str
    symbol: str
    rpc_url: str
    explorer_url: str

    class Config:
        from_attributes = True


class NetworkCreate(NetworkBase):
    pass


class NetworkUpdate(NetworkBase):
    pass


class NetworkSchema(NetworkBase):
    id: int


class Networks(BaseModel):
    items: list[NetworkSchema] = []
    count: int = 0


class CurrencyBase(BaseModel):
    code: str
    name: str
    network_id: int
    address: str
    decimals: int

    class Config:
        from_attributes = True


class CurrencyCreate(CurrencyBase):
    pass


class CurrencyUpdate(CurrencyBase):
    pass


class CurrencySchema(CurrencyBase):
    id: int


class Currencies(BaseModel):
    items: list[CurrencySchema] = []
    count: int = 0


class GameBase(BaseModel):
    name: str
    game_type: str
    currency_id: Optional[int]
    limit_by_ticket: int = 9
    max_limit_grid: int = 90
    price: float = 1.0
    description: Optional[str]
    max_win_amount: Optional[float] = 8.0
    prize: Optional[float] = 1000.0
    country: Optional[str]
    min_ticket_count: int = 1
    scheduled_datetime: Optional[datetime]
    zone: Optional[int] = 1
    repeat: Optional[bool] = False
    repeat_days: Optional[list[int]]
    updated_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class GameCreate(BaseModel):
    name: str
    game_type: GameType
    currency_id: Optional[int]
    limit_by_ticket: int = 9
    max_limit_grid: int = 90
    price: float = 1.0
    description: Optional[str]
    max_win_amount: Optional[float] = 8.0
    prize: Optional[float] = 1000.0
    country: Optional[str]
    min_ticket_count: int = 1
    scheduled_datetime: Optional[datetime]
    zone: Optional[int] = 1
    repeat: Optional[bool] = False
    repeat_days: Optional[list[int]]


class GameUpdate(GameCreate):
    pass


class GameSchema(GameBase):
    id: int


class Games(BaseModel):
    items: list[GameSchema] = []
    count: int = 0


class JackpotBase(BaseModel):
    name: str
    _type: GameType
    percentage: float = 10.0
    image: Optional[str] = "default_image.png"
    country: Optional[str]
    scheduled_datetime: datetime
    tzone: int = 1
    repeat: bool = False
    repeat_days: list[int] = [0, 1, 2, 3, 4, 5, 6]

    updated_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class JackpotCreate(BaseModel):
    name: str
    _type: str
    percentage: float = 10.0
    image: Optional[str] = "default_image.png"
    country: Optional[str]
    scheduled_datetime: datetime
    tzone: int = 1
    repeat: bool = False
    repeat_days: list[int] = [0, 1, 2, 3, 4, 5, 6]


class JackpotUpdate(JackpotCreate):
    pass


class JackpotSchema(JackpotBase):
    id: int


class Jackpots(BaseModel):
    items: list[JackpotSchema] = []
    count: int = 0
