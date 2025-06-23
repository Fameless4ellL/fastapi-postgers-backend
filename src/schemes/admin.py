from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from secrets import token_urlsafe
from typing import Optional, Annotated, Union

import pycountry
import pytz
from fastapi import Query, UploadFile
from phonenumbers import parse, geocoder
from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    computed_field,
    FutureDatetime,
    model_serializer,
    AfterValidator,
    ConfigDict,
    field_validator,
    EmailStr,
    BeforeValidator
)
from pydantic_extra_types.country import CountryAlpha3
from sqlalchemy import case, String, cast

from settings import settings
from src.models.limit import LimitType, Period, RiskLevel, OperationType
from src.models.other import GameStatus, GameType, GameView, JackpotType, RepeatType, TicketStatus
from src.models.user import BalanceChangeHistory, Role, User as DBUser
from src.utils.validators import get_currency_by_id, get_first_currency
from src.schemes.base import Country, Country_by_name, ModPhoneNumber, Image
from src.utils.datastructure import MultiValueStrEnum


class Category(MultiValueStrEnum):
    _5X36 = "5/36", {"limit_by_ticket": 5, "max_limit_grid": 36}
    _6X45 = "6/45", {"limit_by_ticket": 6, "max_limit_grid": 45}
    _10X75 = "10/75", {"limit_by_ticket": 10, "max_limit_grid": 75}
    _15X90 = "15/90", {"limit_by_ticket": 15, "max_limit_grid": 90}


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
    cash: int = 0
    material: Optional[list[Optional[str]]] = []


class UserInfo(User):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    patronymic: Optional[str] = None
    telegram: Optional[str] = None
    telegram_id: Optional[int] = None
    language_code: Optional[str] = None
    email: Optional[str] = None
    kyc_status: Optional[bool] = None
    document: Optional[list[Optional[str]]] = []
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
    number: Optional[str] = None
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


class AdminRoles(MultiValueStrEnum):
    """
    alias List of admin roles
    """
    SUPER_ADMIN = "Super Admin", "super_admin"
    ADMIN = "Admin", "admin"
    GLOBAL_ADMIN = "Global Admin", "global_admin"
    LOCAL_ADMIN = "Local Admin", "local_admin"
    SUPPORT = "Support manager", "support"
    FINANCIER = "Financier", "financier"
    SMM = "SMM", "smm"


class Admin(User):
    username: Optional[str] = None
    email: Optional[str] = None
    fullname: str
    active: bool
    telegram: Optional[str] = None
    role: Role

    @classmethod
    @field_validator("role", mode="after")
    def serialize_role(cls, value: Role) -> str:
        return AdminRoles[value.name].value


class Admins(BaseModel):
    admins: list[Admin] = []
    count: int = 0


class AdminLogin(BaseModel):
    login: str
    password: SecretStr = Field(..., min_length=3, max_length=64, description="Password")
    code: str = Field(default="******", min_length=6, max_length=6, description="2FA code")


class ResetPassword(BaseModel):
    password: SecretStr


class Totp(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, description="2FA code")


class VerifyLink(BaseModel):
    code: str


class ForgotPassword(BaseModel):
    email: EmailStr


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
    prize: Union[float, str] = 1000
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
    price: Decimal = Field(default=1, gt=0, lt=10 ** 7, decimal_places=2, max_digits=7)
    description: Optional[str] = Field("", max_length=500)
    max_win_amount: Optional[Decimal] = Field(default=8, gt=0, lt=10 ** 7, decimal_places=2, max_digits=11)
    prize: Union[float, str] = 0
    country: Optional[CountryAlpha3] = None
    min_ticket_count: int = 1
    scheduled_datetime: Optional[FutureDatetime]
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
        scheduled_datetime = self.scheduled_datetime

        if self.kind == GameView.MATERIAL:
            self.prize = str(self.prize)

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
            "prize": str(self.prize),
            "country": self.country,
            "min_ticket_count": self.min_ticket_count,
            "scheduled_datetime": scheduled_datetime,
            "zone": zone,
            "repeat": bool(len(self.repeat_days)),
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
    prize: Union[float, str] = 1000.0
    image: Optional[Image] = "default_image.png"
    has_tickets: bool = False
    game_type: GameType
    status: GameStatus
    scheduled_datetime: Optional[datetime] = None
    repeat: Optional[bool] = False
    repeat_days: Optional[list[int]] = []
    numbers: Optional[list[Union[int, list[int]]]] = []
    event_start: Optional[datetime] = None
    event_end: Optional[datetime] = None
    updated_at: datetime
    created_at: datetime

    @computed_field
    def category(self) -> str:
        return f"{self.limit_by_ticket}/{self.max_limit_grid}"

    @field_validator("prize")
    def validate_prize(cls, value: Union[float, str]) -> Union[float, str]:
        return str(value)


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

    @classmethod
    @field_validator('image')
    def validate_image(cls, v: Union[UploadFile, None]) -> Union[UploadFile, None]:
        if not v.filename.endswith(('.png', '.jpg', '.jpeg')):
            raise ValueError("Invalid image format")
        return v


class PurchasedTickets(BaseModel):
    pcs: int = 0
    currency: str
    amount: Union[float, int]
    prize: str


class Participant(BaseModel):
    id: int
    user_id: int
    user: Optional[str]
    tickets: int = Field(default=0, ge=0, description="Number of tickets purchased by the user")
    amount: float = 0.0
    date: str


class ParticipantTickets(BaseModel):
    id: int
    user_id: int
    user: Optional[str] = None
    tickets: list[int] = Field(default_factory=list, description="List of ticket numbers purchased by the user")
    number: str
    date: str


class Empty:
    pass


class JackpotBase(BaseAdmin):
    id: int
    name: str
    country: Country
    currency_id: Optional[int] = None
    percentage: Optional[float] = 10.0
    price: float = 1.0
    image: Optional[Image] = "default_image.png"
    game_type: JackpotType = Field(..., alias="_type")
    status: Optional[GameStatus] = None
    repeat: RepeatType = RepeatType.NONE
    has_tickets: bool = False
    scheduled_datetime: Optional[datetime] = None
    fund_start: Optional[datetime] = Field(exclude=True)
    fund_end: Optional[datetime] = Field(exclude=True)
    numbers: Optional[list[Union[int, list[int]]]] = []
    event_start: Optional[datetime] = None
    event_end: Optional[datetime] = None
    updated_at: datetime
    created_at: datetime

    tickets_pcs: int = 0
    amount: Optional[float] = 0.0

    @computed_field
    def fundraising_period(self) -> str:
        return f"{self.fund_start} - {self.fund_end}"


class JackpotCreate(BaseModel):
    name: str
    percentage: float = 10.0
    game_type: JackpotType
    # currency_id: Annotated[int, AfterValidator(get_currency_by_id)]
    country: Optional[CountryAlpha3] = None
    scheduled_datetime: Optional[FutureDatetime]
    repeat: RepeatType = RepeatType.NONE
    fund_start: Optional[FutureDatetime] = None
    fund_end: Optional[FutureDatetime] = None

    @model_serializer
    def ser_model(self):
        # get the timezone from the zone
        try:
            zone = self.scheduled_datetime.tzinfo
            tz = pytz.timezone(zone.tzname(self.scheduled_datetime))
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone('UTC')

        zone = tz.utcoffset(self.scheduled_datetime).total_seconds() // 3600
        scheduled_datetime = self.scheduled_datetime

        fund_start = self.fund_start
        fund_end = self.fund_end

        return {
            "name": self.name,
            "_type": self.game_type,
            "currency_id": get_first_currency(),
            "percentage": self.percentage,
            "country": self.country,
            "scheduled_datetime": scheduled_datetime,
            "tzone": zone,
            "fund_start": fund_start,
            "fund_end": fund_end,
            "repeat_type": self.repeat,
        }


class JackpotUpdate(JackpotCreate):
    pass


class JackpotSchema(BaseAdmin):
    id: int
    name: str
    game_type: JackpotType = Field(..., alias="_type")
    image: Optional[Image] = "default_jackpot.png"
    has_tickets: bool = False
    country: Country
    status: Optional[GameStatus] = None
    scheduled_datetime: Optional[datetime] = None
    fund_start: Optional[datetime] = None
    created_at: datetime


class Jackpots(BaseModel):
    items: list[JackpotSchema] = []
    count: int = 0


@dataclass
class Countries:
    countries: Optional[list[Country_by_name]] = Query(None)


@dataclass
class JackpotFilter(DatePicker, Search, Countries):
    game_type: Optional[list[JackpotType]] = Query(None)


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
    generated_by: Optional[int] = None


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
    # currency_id: Annotated[int, AfterValidator(get_currency_by_id)]
    price: float = 1.0
    x15: float = 1
    x16_20: float = 1
    x21_25: float = 1
    x26_30: float = 1
    x31_35: float = 1
    x36_40: float = 1
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

        currency_id = get_first_currency()

        return {
            "currency_id": currency_id,
            "price": self.price,
            "country": self.country,
            "winnings": winnings
        }


class InstaBingoUpdate(InstaBingoCreate):
    pass


class InstaBingoSchema(InstaBingoBase):
    id: int
    winnings: Optional[dict] = Field(default_factory=dict, exclude=True)

    def get_winnings(self):
        return self.winnings or {}

    @computed_field
    def x15(self) -> Union[int, float]:
        return self.get_winnings().get(str(15), 1)

    @computed_field
    def x16_20(self) -> Union[int, float]:
        return self.get_winnings().get(str(16), 1)

    @computed_field
    def x21_25(self) -> Union[int, float]:
        return self.get_winnings().get(str(21), 1)

    @computed_field
    def x26_30(self) -> Union[int, float]:
        return self.get_winnings().get(str(26), 1)

    @computed_field
    def x31_35(self) -> Union[int, float]:
        return self.get_winnings().get(str(31), 1)

    @computed_field
    def x36_40(self) -> Union[int, float]:
        return self.get_winnings().get(str(36), 1)


class InstaBingos(BaseModel):
    items: list[InstaBingoBase] = []
    count: int = 0


@dataclass
class InstaBingoFilter(DatePicker, Search, Countries):
    pass


class KycBase(BaseAdmin):
    id: int
    country: Country


class KycList(BaseModel):
    items: list[KycBase] = []


class KycCreate(BaseAdmin):
    countries: list[Country_by_name] = []


@dataclass
class KycDelete:
    countries: list[Country_by_name] = Query(None)


class Profile(BaseAdmin):
    id: int
    fullname: str
    telegram: Optional[str] = None
    language_code: Optional[str] = None
    country: Country
    email: Optional[str] = None
    role: Annotated[Role, AfterValidator(lambda v: AdminRoles[v.name])]
    phone_number: Optional[str] = None
    kyc: Optional[bool] = None
    twofa: bool = False
    active: bool
    avatar: Optional[str] = None
    document: Optional[list[str]] = []


class ReferralUsers(BaseAdmin):
    id: int
    username: str
    country: Country
    first_deposit: Optional[float] = None
    created_at: str


class ReferralUsersList(BaseModel):
    items: list[ReferralUsers] = []
    count: int = 0


class AdminStatus(MultiValueStrEnum):
    ACTIVE = "Active", True
    INACTIVE = "Removed", False


@dataclass
class AdminFilter(Search, Countries):
    role: Optional[list[AdminRoles]] = Query(None)
    status: Optional[list[AdminStatus]] = Query(None)


class AdminCreate(BaseAdmin):
    firstname: str
    lastname: str
    email: str
    phone_number: ModPhoneNumber
    role: AdminRoles
    telegram: Optional[str] = None
    country: Optional[CountryAlpha3] = None

    @model_serializer
    def ser_model(self):
        # get country from phone_number
        country_code = parse(f"+{self.phone_number}")
        country = geocoder.region_code_for_number(country_code)
        alpha3 = pycountry.countries.get(alpha_2=country).alpha_3

        return {
            "firstname": self.firstname,
            "lastname": self.lastname,
            "email": self.email,
            "phone_number": self.phone_number,
            "role": self.role.label,
            "telegram": self.telegram,
            "country": alpha3,
        }


class UserTicketWinner(BaseModel):
    id: int
    user_id: int
    user: Optional[str] = None
    numbers: str
    status: Annotated[TicketStatus, BeforeValidator(lambda v: TicketStatus[v])]
    amount: float
    prize: str
    date: str


class Winners(BaseModel):
    items: list[UserTicketWinner] = []
    count: int = 0


class InstaBingoItem(BaseModel):
    ticket_id: int
    user_id: int
    username: str
    country: Country
    created_at: str
    won: Optional[bool] = False
    amount: Optional[float] = None


class InstaBingoList(BaseModel):
    data: list[InstaBingoItem] = []
    count: int = 0


class Operation(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    user_is_blocked: Optional[bool] = False
    country: Country
    sum: float
    transaction_type: Optional[str] = None
    status: Annotated[
        Optional[BalanceChangeHistory.Status],
        BeforeValidator(lambda v: BalanceChangeHistory.Status[v])
    ]
    created_at: Union[datetime, str]
    game_id: Optional[int] = None
    amount: Optional[int] = 1


class Operations(BaseModel):
    items: list[Operation] = []
    count: int = 0


class OperationOrder(MultiValueStrEnum):
    CREATED = "created", BalanceChangeHistory.created_at.asc()
    CREATED_ = "-created", BalanceChangeHistory.created_at.desc()
    AMOUNT = "amount", BalanceChangeHistory.change_amount.asc()
    AMOUNT_ = "-amount", BalanceChangeHistory.change_amount.desc()
    TYPE = "change_type", BalanceChangeHistory.change_type.asc()
    TYPE_ = "-change_type", BalanceChangeHistory.change_type.desc()
    STATUS = "status", case(
        {
            BalanceChangeHistory.Status.BLOCKED.name: 1,
            BalanceChangeHistory.Status.CANCELED.name: 2,
            BalanceChangeHistory.Status.INSUFFICIENT_FUNDS.name: 3,
            BalanceChangeHistory.Status.PENDING.name: 4,
            BalanceChangeHistory.Status.SUCCESS.name: 5,
            BalanceChangeHistory.Status.WEB3_ERROR.name: 6
        },
        value=cast(BalanceChangeHistory.status, String)
    )
    STATUS_ = "-status", case(
        {
            BalanceChangeHistory.Status.WEB3_ERROR.name: 1,
            BalanceChangeHistory.Status.SUCCESS.name: 2,
            BalanceChangeHistory.Status.PENDING.name: 3,
            BalanceChangeHistory.Status.INSUFFICIENT_FUNDS.name: 4,
            BalanceChangeHistory.Status.CANCELED.name: 5,
            BalanceChangeHistory.Status.BLOCKED.name: 6
        },
        value=cast(BalanceChangeHistory.status, String)
    )
    COUNTRY = "country", DBUser.country.asc()
    COUNTRY_ = "-country", DBUser.country.desc()


class OperationFilterType(MultiValueStrEnum):
    WITHDRAWAL = "withdraw", "withdraw"
    PURCHASE = "purchase", "ticket purchase"
    PENALTY = "penalty", "penalty"
    DEPOSIT = "deposit", "deposit"
    WON = "won", "won"


@dataclass
class OperationFilter(DatePicker, Countries, Search):
    export: bool = False
    status: Optional[list[BalanceChangeHistory.Status]] = Query(None)
    type: Optional[list[OperationFilterType]] = Query(None)
    order_by: list[OperationOrder] = Query(default=[OperationOrder.CREATED_])


class LimitBase(BaseModel):
    id: int
    type: LimitType
    value: Decimal
    currency: Optional[str] = None
    operation_type: Annotated[
        OperationType,
        BeforeValidator(lambda v: getattr(OperationFilterType, v, OperationType.ALL))
    ]
    period: Period
    kyc: Optional[bool] = False
    status: Optional[bool] = True
    risk: Optional[RiskLevel] = None
    created_at: datetime
    updated_at: datetime
    last_editer: Optional[int] = None


class Limits(BaseModel):
    items: list[LimitBase] = []
    count: int = 0


class LimitCreate(BaseModel):
    type: LimitType
    value: Annotated[Decimal, Field(decimal_places=2, ge=0, lt=10 ** 7, max_digits=7)]
    operation_type: OperationType
    period: Period
    kyc: bool = False
    risk: RiskLevel


class LimitUpdate(LimitCreate):
    pass


class JackpotWinner(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    username: Optional[int] = None
    numbers: Optional[int] = None
    tickets_pcs: int = 0
