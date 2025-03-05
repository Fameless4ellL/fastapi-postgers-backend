from decimal import Decimal
from typing import Annotated, Optional
from pydantic import BaseModel, Field, AfterValidator
from enum import Enum


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

    JACKPOT = "Jackpot", "Jackpot"
    GAME = "game", "Game"


class Game(BaseModel):
    id: int
    name: str
    image: Optional[str] = None
    currency: Optional[str] = None
    status: str
    price: float
    prize: float
    max_limit_grid: int
    endtime: float
    created: float


class GameInstance(Game):
    description: str
    game_type: str
    limit_by_ticket: int
    min_ticket_count: int
    max_limit_grid: int
    price: float
    prize: float
    min_ticket_count: int


class Games(BaseModel):
    games: list[Game] = Field(default=[])
    count: int = 0


class BuyTicket(BaseModel):
    numbers: list[set[int]]
    demo: bool = False


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
    won: Optional[bool]
    amount: float = 0
    demo: Optional[bool]
    created: float


class Tickets(BaseModel):
    tickets: list[Ticket] = Field(default=[])
    count: int = 0


class MyGame(Game):
    max_limit_grid: Optional[int] = None
    won: float = 0


class MyGames(BaseModel):
    games: list[MyGame] = Field(default=[])
    count: int = 0


class Deposit(BaseModel):
    hash: str


class Withdraw(BaseModel):
    amount: float = 0
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
