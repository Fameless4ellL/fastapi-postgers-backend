from typing import Optional

from pydantic import BaseModel, Field, SecretStr
from pydantic_extra_types.country import CountryAlpha3

from src.schemes.base import ModPhoneNumber


class CheckCode(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, description="SMS code")


class UserLogin(CheckCode):
    username: str = Field(default="", exclude=True, deprecated=True)
    phone_number: ModPhoneNumber
    password: Optional[SecretStr] = Field(default="", exclude=True, deprecated=True)


class UserRegister(BaseModel):
    username: str = Field(default="", exclude=True, deprecated=True)
    phone_number: ModPhoneNumber
    country: CountryAlpha3
    refferal_code: Optional[str] = None


class SendCode(BaseModel):
    phone_number: ModPhoneNumber


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
