from decimal import Decimal

import pycountry
from typing import Annotated, Optional
from pydantic import BaseModel, computed_field, AfterValidator, Field
from pydantic_extra_types.country import CountryAlpha3
from pydantic_extra_types.language_code import LanguageAlpha2

from src.models import BalanceChangeHistory
from src.utils.validators import url_for


class UserBalance(BaseModel):
    id: int
    network: str
    currency: str
    balance: float


class UserBalanceList(BaseModel):
    items: list[UserBalance] = []


class KYC(BaseModel):
    first_name: str
    last_name: str
    patronomic: Optional[str] = None


class Usersettings(BaseModel):
    locale: LanguageAlpha2
    country: CountryAlpha3


class Address(BaseModel):
    base58: str
    evm: str


class Docs(BaseModel):
    id: Optional[int] = None
    file: Annotated[
        Optional[str],
        AfterValidator(lambda x: url_for("static/kyc", path=x) if x is not None else None)
    ] = None
    created_at: Optional[float] = None


class KYCProfile(KYC):
    documents: Optional[list[Docs]] = None


class Profile(BaseModel):
    username: Optional[str]
    kyc: Optional[KYCProfile] = None
    kyc_approved: bool = False
    balance: float
    address: Address
    locale: str = "en"
    notifications: bool = False
    country: Annotated[
        str,
        AfterValidator(lambda x: pycountry.countries.get(alpha_3=x))
    ] = Field(exclude=True)

    @computed_field
    def country_alpha3(self) -> str:
        return self.country.alpha_3

    @computed_field
    def country_name(self) -> str:
        return self.country.name

    @computed_field
    def country_flag(self) -> str:
        return self.country.flag


class NotificationItem(BaseModel):
    id: int
    head: str
    body: str
    args: dict
    created: float


class Notifications(BaseModel):
    items: list[NotificationItem] = []
    count: int = 0


class Transaction(BaseModel):
    id: int
    amount: Decimal
    type: str
    currency: str
    status: BalanceChangeHistory.Status
    created: float


class Transactions(BaseModel):
    items: list[Transaction] = []
    count: int = 0