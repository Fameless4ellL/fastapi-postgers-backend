import pycountry
from typing import Annotated
from pydantic import BaseModel, computed_field, AfterValidator, Field
from pydantic_extra_types.country import CountryAlpha3
from pydantic_extra_types.language_code import LanguageAlpha2


class UserBalance(BaseModel):
    network: str
    currency: str
    balance: float


class KYC(BaseModel):
    first_name: str
    last_name: str


class Usersettings(BaseModel):
    locale: LanguageAlpha2
    country: CountryAlpha3


class Address(BaseModel):
    base58: str
    evm: str


class Profile(BaseModel):
    username: str
    balance: float
    address: Address
    locale: str
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
