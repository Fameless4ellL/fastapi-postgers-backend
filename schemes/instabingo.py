from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class InstaBingoInfo(BaseModel):
    id: int = 1
    price: Decimal = "1"
    currency: str = "USDT"
