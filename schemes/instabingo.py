from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class InstaBingoInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = 1
    price: Decimal = "1"
    currency: str = "USDT"
