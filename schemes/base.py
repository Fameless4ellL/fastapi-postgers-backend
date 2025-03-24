from typing import Annotated, Optional, Union
import pycountry
from pydantic import BaseModel, Field, Json, BeforeValidator, AfterValidator
from pydantic_extra_types.country import CountryShortName
from fastapi.params import Form as FormType


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
