import pycountry
from dataclasses import dataclass
from secrets import token_urlsafe
from pydantic_extra_types.phone_numbers import PhoneNumber
from phonenumbers import parse, geocoder
from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    WrapSerializer,
    computed_field,
    FutureDatetime,
    model_serializer,
    AfterValidator,
    ConfigDict
)
import pytz
from typing import Optional, Annotated, Any, Union
from datetime import datetime, date
from pydantic_extra_types.country import CountryAlpha3
from fastapi import Query, UploadFile

from models.other import GameStatus, GameType, GameView
from models.user import BalanceChangeHistory
from routers.utils import get_currency_by_id, url_for
from schemes.base import Country
from settings import settings
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
    MONETARY = "Monetary", GameView.MONETARY
    MATERIAL = "Clothing", GameView.MATERIAL


class BaseAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class User(BaseModel):
    username: str
    id: int
    phone_number: Optional[str] = None
    country: Country


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
    model_config = ConfigDict(from_attributes=True)

    chain_id: int
    name: str
    symbol: str
    rpc_url: str
    explorer_url: str


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
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    network_id: int
    address: str
    decimals: Optional[int]


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
    repeat_days: Optional[list[int]] = []

    @model_serializer
    def ser_model(self):
        # get the timezone from the zone
        try:
            zone = self.scheduled_datetime.tzinfo
            tz = pytz.timezone(zone.tzname(self.scheduled_datetime))
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('UTC')

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
    description: Optional[str] = ""
    country: Country
    currency_id: Optional[int] = None
    limit_by_ticket: int = 15
    max_limit_grid: int = 90
    max_win_amount: Optional[float] = 8.0
    min_ticket_count: int = 1
    price: float = 1.0
    prize: Optional[float] = 1000.0
    image: Optional[Image] = "default_image.png"
    has_tickets: bool = False
    game_type: GameType
    status: GameStatus
    repeat: Optional[bool] = False
    repeat_days: Optional[list[int]]
    deleted: Optional[bool] = False
    numbers: Optional[list[Union[int, list[int]]]] = []
    event_start: Optional[datetime] = None
    event_end: Optional[datetime] = None
    updated_at: datetime
    created_at: datetime

    @computed_field
    def category(self) -> str:
        return f"{self.limit_by_ticket}/{self.max_limit_grid}"


class Games(BaseModel):
    items: list[GameSchema] = []
    count: int = 0


@dataclass
class Search:
    filter: Optional[str] = Query(None)


@dataclass
class DatePicker:
    date_from: Optional[date] = Query(None)
    date_to: Optional[date] = Query(None)


@dataclass
class GameFilter(DatePicker, Search):
    game_type: Optional[list[GameType]] = Query(None)
    category: Optional[list[Category]] = Query(None)
    kind: Optional[list[GameView]] = Query(None)


@dataclass
class GameUpload:
    image: Union[UploadFile, None] = None


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
    link: str = Field(exclude=True)
    user_count: int = 0
    comment: Optional[str]
    created_at: datetime

    @computed_field
    def url(self) -> str:
        return f"{settings.web_app_url}/?ref={self.link}"


class ReferralCreate(BaseAdmin):
    name: str
    comment: Optional[str]

    @model_serializer
    def ser_model(self):
        code = token_urlsafe(5)

        return {
            "name": self.name,
            "comment": self.comment,
            "link": code
        }


class ReferralUpdate(ReferralCreate):
    pass


class ReferralSchema(ReferralBase):
    id: int


class Referrals(BaseModel):
    items: list[ReferralSchema] = []
    count: int = 0


class ReferralStatus(MultiValueStrEnum):
    ACTIVE = "Active", False
    INACTIVE = "Removed", True


@dataclass
class ReferralFilter(Search):
    status: Optional[list[ReferralStatus]] = Query(None)


class InstaBingoBase(BaseAdmin):
    id: int
    country: Country
    price: float = 1.0
    currency_id: Optional[int] = None
    deleted: Optional[bool] = False


class InstaBingoCreate(BaseAdmin):
    currency_id: Annotated[int, AfterValidator(get_currency_by_id)]
    price: float = 1.0
    x15: int = 1
    x16_20: int = 1
    x21_25: int = 1
    x26_30: int = 1
    x31_35: int = 1
    x36_40: int = 1
    country: Optional[CountryAlpha3] = None

    @model_serializer
    def ser_model(self):
        winnings = {}
        for i in range(15, 41):
            start = "15"
            key = ''
            if i == 16:
                start = "16"
                key = '_20'
            elif i == 21:
                start = "21"
                key = '_25'
            elif i == 26:
                start = "26"
                key = '_30'
            elif i == 31:
                start = "31"
                key = '_35'
            elif i == 36:
                start = "36"
                key = '_40'

            winnings[i] = getattr(self, f"x{start}{key}")

        return {
            "currency_id": self.currency_id,
            "price": self.price,
            "country": self.country,
            "winnings": winnings
        }


class InstaBingoUpdate(InstaBingoCreate):
    pass


class InstaBingoSchema(InstaBingoBase):
    id: int
    winnings: Optional[dict[int, int]] = Field(default_factory=dict, exclude=True)

    def get_winnings(self):
        return self.winnings if self.winnings else {}

    @computed_field
    def x15(self) -> int:
        return self.get_winnings().get(15, 1)

    @computed_field
    def x16_20(self) -> int:
        return self.get_winnings().get(16, 1)

    @computed_field
    def x21_25(self) -> int:
        return self.get_winnings().get(21, 1)

    @computed_field
    def x26_30(self) -> int:
        return self.get_winnings().get(26, 1)

    @computed_field
    def x31_35(self) -> int:
        return self.get_winnings().get(31, 1)

    @computed_field
    def x36_40(self) -> int:
        return self.get_winnings().get(36, 1)


class InstaBingos(BaseModel):
    items: list[InstaBingoBase] = []
    count: int = 0


@dataclass
class InstaBingoFilter(DatePicker, Search):
    countries: Optional[list[CountryAlpha3]] = Query(None)


class KycBase(BaseAdmin):
    id: int
    countries: list[CountryAlpha3] = []


class KycCreate(BaseAdmin):
    countries: list[CountryAlpha3] = []


class Profile(BaseAdmin):
    id: int
    fullname: str
    telegram: Optional[str] = None
    language_code: Optional[str] = None
    country: Country
    email: Optional[str] = None
    role: str
    phone_number: Optional[str] = None
    kyc: Optional[bool] = None
    avatar: Optional[str] = None
    document: Optional[str] = None


class ReferralUsers(BaseAdmin):
    id: int
    username: str
    country: Country
    first_deposit: float


class ReferralUsersList(BaseModel):
    items: list[ReferralUsers] = []
    count: int = 0


class AdminRoles(MultiValueStrEnum):
    SUPER_ADMIN = "Super Admin", "super_admin"
    ADMIN = "Admin", "admin"
    GLOBAL_ADMIN = "Global Admin", "global_admin"
    LOCAL_ADMIN = "Local Admin", "local_admin"
    SUPPORT = "Support manager", "support"
    FINANCE = "Financier", "financier"
    SMM = "SMM", "smm"


class AdminStatus(MultiValueStrEnum):
    ACTIVE = "Active", False
    INACTIVE = "Inactive", True


@dataclass
class AdminFilter(Search):
    role: Optional[list[AdminRoles]] = Query(None)
    countries: Optional[list[CountryAlpha3]] = Query(None)
    status: Optional[list[AdminStatus]] = Query(None)


class AdminCreate(BaseAdmin):
    firstname: str
    lastname: str
    email: str
    phone_number: PhoneNumber
    role: AdminRoles
    telegram: Optional[str] = None
    country: CountryAlpha3

    @model_serializer
    def ser_model(self):
        # get country from phone_number
        country_code = parse(self.phone_number)
        # country = geocoder.region_code_for_number(country_code)
        phone_number = f"{country_code.country_code}{country_code.national_number}"

        country = geocoder.region_code_for_number(country_code)
        alpha2 = pycountry.countries.get(alpha_2=country).alpha_3

        return {
            "firstname": self.firstname,
            "lastname": self.lastname,
            "email": self.email,
            "phone_number": phone_number,
            "role": self.role,
            "telegram": self.telegram,
            "country": alpha2,
        }