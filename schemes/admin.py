from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    WrapSerializer,
    computed_field,
    FutureDatetime,
    model_serializer,
    AfterValidator,
)
import pytz
from typing import Optional, Annotated, Any
from datetime import datetime, date
from pydantic_extra_types.country import CountryAlpha3
from fastapi import Query

from models.other import GameStatus, GameType, GameView
from models.user import BalanceChangeHistory
from routers.utils import get_currency_by_id, url_for
from utils.datastructure import MultiValueStrEnum


def get_image(value: Any, handler, info) -> str:
    return url_for("static", filename=value)


Image = Annotated[str, WrapSerializer(get_image)]


class Category(MultiValueStrEnum):
    _5x36 = "5/36", {"limit_by_ticket": 5, "max_limit_grid": 36}
    _6x45 = "6/45", {"limit_by_ticket": 6, "max_limit_grid": 45}
    _10x75 = "10/75", {"limit_by_ticket": 10, "max_limit_grid": 75}
    _15x90 = "15/90", {"limit_by_ticket": 15, "max_limit_grid": 90}


class GameViewType(MultiValueStrEnum):
    MONETARY = "Monetary", "monetary"
    MATERIAL = "Clothing", "material"


class BaseAdmin(BaseModel):
    class Config:
        from_attributes = True


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


class History(BaseModel):
    id: int
    change_type: str
    amount: float
    date_and_time: str
    status: Optional[BalanceChangeHistory.Status] = BalanceChangeHistory.Status.PENDING


class HistoryList(BaseModel):
    items: list[History] = []
    count: int = 0


class WalletBase(BaseModel):
    id: int
    address: str
    date_and_time: str


class BalanceBase(BaseModel):
    id: int
    currency: str
    balance: float


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
    decimals: Optional[int]

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


class GameBase(BaseAdmin):
    name: str
    game_type: str
    currency_id: Annotated[int, AfterValidator(get_currency_by_id)]
    limit_by_ticket: int = 15
    max_limit_grid: int = 90
    price: float = 1.0
    description: Optional[str]
    max_win_amount: Optional[float] = 8.0
    prize: Optional[float] = 1000.0
    image: Optional[Image] = "default_image.png"
    country: Optional[str]
    min_ticket_count: int = 1
    scheduled_datetime: Optional[datetime]
    zone: Optional[int] = 1
    repeat: Optional[bool] = False
    repeat_days: Optional[list[int]]
    updated_at: datetime
    created_at: datetime


class GameCreate(BaseAdmin):
    name: str
    game_type: GameType
    kind: GameView
    currency_id: Annotated[int, AfterValidator(get_currency_by_id)]
    category: Category
    price: float = 1.0
    description: Optional[str] = Field("", max_length=500)
    max_win_amount: Optional[float] = 8.0
    prize: Optional[float] = 1000.0
    country: Optional[CountryAlpha3] = None
    min_ticket_count: int = 1
    scheduled_datetime: Optional[FutureDatetime]
    repeat: Optional[bool] = False
    repeat_days: Optional[list[int]]

    @model_serializer
    def ser_model(self):
        # get the timezone from the zone
        zone = self.scheduled_datetime.tzinfo
        tz = pytz.timezone(zone.tzname(self.scheduled_datetime))
        zone = tz.utcoffset(self.scheduled_datetime).total_seconds() // 3600
        scheduled_datetime = self.scheduled_datetime.astimezone(tz).isoformat()

        if self.scheduled_datetime and self.scheduled_datetime.tzinfo is not None:
            scheduled_datetime = self.scheduled_datetime.replace(tzinfo=None)
        else:
            scheduled_datetime = self.scheduled_datetime

        return {
            "name": self.name,
            "game_type": self.game_type,
            "kind": self.kind,
            "currency_id": self.currency_id,
            "limit_by_ticket": self.category.label['limit_by_ticket'],
            "max_limit_grid": self.category.label['max_limit_grid'],
            "price": self.price,
            "description": self.description,
            "max_win_amount": self.max_win_amount,
            "prize": self.prize,
            "country": self.country,
            "min_ticket_count": self.min_ticket_count,
            "scheduled_datetime": scheduled_datetime,
            "zone": zone,
            "repeat": self.repeat,
            "repeat_days": self.repeat_days,
        }


class GameUpdate(GameCreate):
    scheduled_datetime: Optional[datetime]


class GameSchema(BaseAdmin):
    id: int
    name: str
    kind: Optional[GameView] = GameView.MONETARY
    currency_id: Optional[int] = None
    limit_by_ticket: int = 15
    max_limit_grid: int = 90
    image: Optional[Image] = "default_image.png"
    game_type: str
    status: GameStatus
    deleted: Optional[bool] = False
    updated_at: datetime
    created_at: datetime

    @computed_field
    def category(self) -> str:
        return f"{self.limit_by_ticket}/{self.max_limit_grid}"


class Games(BaseModel):
    items: list[GameSchema] = []
    count: int = 0


class GameFilter:
    def __init__(
        self,
        game_type: Annotated[list[Annotated[GameType, Query()]], Query()] = None,
        filter: Annotated[str, Query()] = None,
        category: Annotated[list[Annotated[Category, Query()]], Query()] = None,
        kind: Annotated[list[Annotated[GameViewType, Query()]], Query()] = None,
        date_from: Annotated[date, Query()] = None,
        date_to: Annotated[date, Query()] = None,
    ):
        self.game_type = game_type
        self.filter = filter
        self.kind = kind
        self.category = category
        self.date_from = date_from
        self.date_to = date_to


class Empty:
    pass


class JackpotBase(BaseAdmin):
    name: str
    _type: GameType
    percentage: float = 10.0
    image: Optional[Image] = "default_jackpot.png"
    country: Optional[str]
    scheduled_datetime: datetime
    tzone: int = 1
    repeat: bool = False
    status: GameStatus
    repeat_days: list[int] = [0, 1, 2, 3, 4, 5, 6]

    updated_at: datetime
    created_at: datetime


class JackpotCreate(BaseModel):
    name: str
    _type: str
    percentage: float = 10.0
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


class ReferralBase(BaseAdmin):
    name: str
    deleted: bool
    link: str
    comment: Optional[str]
    created_at: datetime


class ReferralCreate(BaseAdmin):
    name: str
    link: str
    comment: Optional[str]


class ReferralUpdate(ReferralCreate):
    pass


class ReferralSchema(ReferralBase):
    id: int


class Referrals(BaseModel):
    items: list[ReferralSchema] = []
    count: int = 0


class ReferralFilter:
    def __init__(
        self,
        query: Optional[str] = "",
        status: Optional[bool] = None,
    ):
        self.query = query
        self.status = status
