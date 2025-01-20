from typing import Optional
from pydantic import BaseModel


class WidgetLogin(BaseModel):
    id: int
    hash: str
    username: str
    auth_date: int
    first_name: str
    last_name: str
    photo_url: str
