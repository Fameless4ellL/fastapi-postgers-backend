from pydantic import BaseModel, Field, SecretStr
from pydantic_extra_types.phone_numbers import PhoneNumber
from pydantic_extra_types.country import CountryAlpha3
from typing import Optional


class UserLogin(BaseModel):
    username: str = ""
    phone_number: str
    code: str = Field(..., min_length=6, max_length=6, description="SMS code")
    password: Optional[SecretStr] = Field(default="", exclude=True, deprecated=True)


class UserCreate(UserLogin):
    country: CountryAlpha3


class SendCode(BaseModel):
    phone_number: PhoneNumber


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminLogin(BaseModel):
    username: str
    password: SecretStr = Field(..., min_length=8, max_length=64, description="Password")


class CheckCode(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, description="SMS code")
