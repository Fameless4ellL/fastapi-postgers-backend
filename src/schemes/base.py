from typing import Annotated, Optional, Union, Any
import pycountry
from phonenumbers import parse
from pydantic import BaseModel, Field, Json, BeforeValidator, AfterValidator, WrapSerializer
from pydantic_extra_types.country import CountryShortName
from fastapi.params import Form as FormType
from pydantic_extra_types.phone_numbers import PhoneNumber

from src.utils.validators import url_for


def get_image(value: Any, handler, info) -> str:
    return url_for("static", filename=value)


Image = Annotated[str, WrapSerializer(get_image)]


class BadResponse(BaseModel):
    message: str = Field(default="Bad Request")


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
