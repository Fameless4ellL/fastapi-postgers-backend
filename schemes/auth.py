from pydantic import BaseModel, Field, SecretStr


class UserLogin(BaseModel):
    username: str = ""
    phone_number: str = ""
    code: str = Field(..., min_length=6, max_length=6, description="SMS code")
    password: SecretStr


class UserCreate(UserLogin):
    username: str
    phone_number: str
