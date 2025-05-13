from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class Winnings(BaseModel):
    winnings: Optional[dict[int, int]] = Field(default_factory=dict, exclude=True)

    def get_winnings(self):
        return self.winnings if self.winnings else {}

    @computed_field
    def x15(self) -> int:
        return self.get_winnings().get(15, 1)

    @computed_field
    def x16_20(self) -> int:
        return self.get_winnings().get(16, 1)

    @computed_field
    def x21_25(self) -> int:
        return self.get_winnings().get(21, 1)

    @computed_field
    def x26_30(self) -> int:
        return self.get_winnings().get(26, 1)

    @computed_field
    def x31_35(self) -> int:
        return self.get_winnings().get(31, 1)

    @computed_field
    def x36_40(self) -> int:
        return self.get_winnings().get(36, 1)


class InstaBingoInfo(Winnings):
    id: int = 1
    price: Decimal = Field(default=Decimal(1))
    currency: str = "USDT"


class InstaBingoResults(Winnings):
    won: bool = False
    gen: list[int]
    won_amount: Decimal
    numbers: list[int] = Field(default_factory=list)