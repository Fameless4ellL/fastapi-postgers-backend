from pydantic import BaseModel, SecretStr


class UserLogin(BaseModel):
    username: str = ""
    phone_number: str = ""
    password: SecretStr


class UserCreate(UserLogin):
    username: str
