from pydantic import BaseModel, Field, Json
from fastapi.params import Form as FormType


class BadResponse(BaseModel):
    message: str = Field(default="Bad Request")


class Country(BaseModel):
    alpha_3: str
    name: str


class JsonForm(Json, FormType):
    ...
