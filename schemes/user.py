from pydantic import BaseModel


class Profile(BaseModel):
    username: str
    balance: float
    address: str
    locale: str
    country: str
