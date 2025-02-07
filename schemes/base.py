from pydantic import BaseModel, Field


class BadResponse(BaseModel):
    message: str = Field(default="Bad Request")


class Country(BaseModel):
    alpha_3: str
    name: str