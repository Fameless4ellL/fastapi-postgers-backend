import json
from decimal import Decimal

import pycountry
from typing import Annotated, Optional, Union
from pydantic import BaseModel, computed_field, AfterValidator, Field
from pydantic_extra_types.country import CountryAlpha3
from pydantic_extra_types.language_code import LanguageAlpha2

from src.models import BalanceChangeHistory
from src.utils.validators import url_for, url_for_encoded


class UserBalance(BaseModel):
    id: int
    network: str
    currency: str
    balance: float


class UserBalanceList(BaseModel):
    items: list[UserBalance] = []


class KYC(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    patronomic: Optional[str] = None


class Usersettings(BaseModel):
    locale: LanguageAlpha2
    country: CountryAlpha3


class Address(BaseModel):
    base58: str
    evm: str


class Docs(BaseModel):
    id: Optional[int] = None
    filename: Optional[str] = None
    created_at: Optional[float] = None

    @computed_field
    def data(self) -> Union[str, None]:
        if self.filename is not None:
            return url_for_encoded("static/kyc", path=self.filename)
        return

    @computed_field
    def file(self) -> Union[str, None]:
        if self.filename is not None:
            return url_for("static/kyc", path=self.filename)
        return


class KYCProfile(KYC):
    documents: Optional[list[Docs]] = None


class Profile(BaseModel):
    username: Optional[str] = None
    phone_number: str
    kyc_approved: Optional[bool] = False
    balance: Optional[float] = 0
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
    args_: str
    created: float

    @computed_field
    def args(self) -> dict:
        return json.loads(self.args_)


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