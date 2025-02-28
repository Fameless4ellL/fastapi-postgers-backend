import pycountry
from typing import Annotated
from pydantic import BaseModel, computed_field, AfterValidator, Field


class UserBalance(BaseModel):
    network: str
    currency: str
    balance: float


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
