from decimal import Decimal
from typing import Annotated, Optional, Union
from pydantic import BaseModel, Field, AfterValidator, field_validator
from annotated_types import Len
from enum import Enum

from src.models import GameType, GameView
from src.schemes.base import Image

CommaList = Annotated[str, AfterValidator(lambda x: set(x.split(",")))]

class TicketMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class MyGamesType(str, Enum):
    def __new__(cls, value, model):
        obj = str.__new__(cls, [value])
        obj._value_ = value
        obj.model = model
        return obj

    model: str

    JACKPOT = "jackpot", "Jackpot"
    GAME = "game", "Game"
    INSTA_BINGO = "insta_bingo", "InstaBingo"


class Game(BaseModel):
    id: int
    name: str
    image: Optional[str] = None
    currency: Optional[str] = None
    status: str
    price: Optional[float] = None
    prize: Union[float, str] = None
    max_limit_grid: int
    endtime: float
    created: float


class GameInstance(Game):
    description: str
    game_type: GameType
    kind: GameView
    limit_by_ticket: int
    min_ticket_count: int
    max_limit_grid: int
    price: float
    prize: Union[float, str] = None


class Games(BaseModel):
    games: list[Game] = Field(default=[])
    count: int = 0


class BuyTicket(BaseModel):
    numbers: list[set[int]]
    demo: bool = False


class BuyInstaTicket(BaseModel):
    numbers: Annotated[list[int], Len(15, 15)]

    @field_validator("numbers", mode="after")
    def check_numbers(cls, v: list[int]) -> list[int]:
        if len(set(v)) != 15:
            raise ValueError("Invalid numbers, should be 15")
        return v


class EditTicket(BaseModel):
    numbers: list[set[int]]
    edited_numbers: set[int]


class GenTicket:
    def __init__(
        self,
        mode: TicketMode = TicketMode.AUTO,
        quantity: int = 1,
        numbers: Optional[list[set[int]]] = None
    ):
        self.mode = mode
        self.quantity = quantity
        self.numbers = numbers


class Ticket(BaseModel):
    id: int
    game_instance_id: int
    currency: Optional[str] = None
    numbers: list[int]
    won: Optional[bool] = False
    amount: Decimal = 0
    demo: Optional[bool] = False
    created: float


class Tickets(BaseModel):
    tickets: list[Ticket] = Field(default=[])
    count: int = 0


class MyGame(Game):
    status: Annotated[str, AfterValidator(lambda x: x.lower())]
    image: Optional[Image] = None
    max_limit_grid: Optional[int] = None
    game_id: Optional[int] = None
    won: Optional[bool] = False
    demo: Optional[bool] = False
    total_amount: float = 0
    endtime: Union[float, str]
    created: Union[float, str]


class MyGames(BaseModel):
    games: list[MyGame] = Field(default=[])
    count: int = 0


class Deposit(BaseModel):
    hash: str


class Withdraw(BaseModel):
    amount: Decimal = Field(decimal_places=2, ge=0)
    address: str


class Jackpot(BaseModel):
    id: int
    jackpot_id: int
    status: str
    image: Optional[str] = None
    prize: float
    percentage: float
    endtime: float
    created: float
