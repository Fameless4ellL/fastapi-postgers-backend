from pydantic import BaseModel


class Profile(BaseModel):
    username: str
    balance: int
    locale: str
    country: str
