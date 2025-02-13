from pydantic import BaseModel


class Profile(BaseModel):
    username: str
    balance: int
    address: str
    locale: str
    country: str
