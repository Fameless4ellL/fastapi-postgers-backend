from decimal import Decimal
from typing import Annotated, Optional
from pydantic import BaseModel, ConfigDict
from enum import Enum


class InstaBingoInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = 1
    price: Decimal = 1
    prize: Decimal = 1000
    currency: str = "USDT"
