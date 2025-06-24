from typing import Annotated, Optional, Union
import pycountry
from phonenumbers import parse
from pydantic import BaseModel, Field, Json, BeforeValidator, AfterValidator
from pydantic_extra_types.country import CountryShortName
from fastapi.params import Form as FormType
from pydantic_extra_types.phone_numbers import PhoneNumber


class BadResponse(BaseModel):
    message: str = Field(default="Bad Request")


class ErrorMessage(BaseModel):
    """An error message schema."""
    message: str
    code_error: str


class CountryBase(BaseModel):
    model_config = {"from_attributes": True}

    alpha_3: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    flag: Optional[str] = Field(default=None)


class JsonForm(Json, FormType):
    ...


Country = Annotated[
    Union[CountryBase, None],
    BeforeValidator(lambda x: pycountry.countries.get(alpha_3=str(x)))
]
Country_by_name = Annotated[
    CountryShortName,
    AfterValidator(lambda x: x.alpha3)
]
ModPhoneNumber = Annotated[
    PhoneNumber,
    BeforeValidator(lambda x: f"+{x}" if not x.startswith("+") else x),
    AfterValidator(lambda x: parse(x)),
    AfterValidator(lambda x: f"{x.country_code}{x.national_number}")
]
