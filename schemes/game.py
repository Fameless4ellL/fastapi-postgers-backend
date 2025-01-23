from typing import Annotated
from pydantic import BaseModel, Field, AfterValidator


CommaList = Annotated[str, AfterValidator(lambda x: set(x.split(",")))]


class Game(BaseModel):
    id: int
    name: str
    created: float


class GameInstance(Game):
    description: str
    game_type: str
    limit_by_ticket: int
    min_ticket_count: int
    max_limit_grid: int
    price: float
    min_ticket_count: int


class Games(BaseModel):
    games: list[Game] = Field(default=[])
    count: int = 0


class BuyTicket(BaseModel):
    numbers: list[set[int]]
    demo: bool = False


class Ticket(BaseModel):
    id: int
    game_instance_id: int
    numbers: list[int]
    demo: bool
    created: float


class Tickets(BaseModel):
    tickets: list[Ticket] = Field(default=[])
    count: int = 0
