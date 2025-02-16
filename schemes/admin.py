from pydantic import BaseModel, Field, SecretStr
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


class CurrencyCreate(NetworkBase):
    pass


class CurrencyUpdate(NetworkBase):
    pass


class CurrencySchema(NetworkBase):
    id: int


class Currencies(BaseModel):
    items: list[CurrencySchema] = []
    count: int = 0
