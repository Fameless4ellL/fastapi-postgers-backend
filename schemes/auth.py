from pydantic import BaseModel, Field, SecretStr
from pydantic_extra_types.phone_numbers import PhoneNumber


class UserLogin(BaseModel):
    username: str = ""
    phone_number: str = ""
    password: SecretStr


class UserCreate(BaseModel):
    username: str
    phone_number: PhoneNumber
    code: str = Field(..., min_length=6, max_length=6, description="SMS code")
    password: SecretStr
