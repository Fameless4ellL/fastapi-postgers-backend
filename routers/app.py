from typing import Annotated
from fastapi import Depends, Path, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, exists
from models.db import get_db
from models.user import Balance, User
from models.other import Game, GameInstance, GameStatus, Ticket
from routers import public
from routers.utils import generate_game, get_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from schemes.base import BadResponse
from schemes.game import BuyTicket, Games, GameInstance as GameInstanceModel, Tickets
from schemes.tg import WidgetLogin
from utils.signature import TgAuth
from settings import settings


@public.post("/tg/login")
async def tg_login(item: WidgetLogin):
    """
        Для логина в telegram mini app
    """
    print(settings.bot_token)
    if not TgAuth(item, settings.bot_token.encode("utf-8")).check_hash():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Bad Request"
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.post("/deposit")
async def deposit(user: User = Depends(get_user)):
    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.post("/withdraw")
async def withdraw(user: User = Depends(get_user)):
    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.get(
    "/games",
    responses={404: {"model": BadResponse}, 200: {"model": Games}}
)
async def game_instances(
    db: AsyncSession = Depends(get_db),
    offset: int = 0,
    limit: int = 10
):
    result = await db.execute(
        select(GameInstance)
        .options(joinedload(GameInstance.game).load_only(Game.name))
        .filter(GameInstance.status == GameStatus.PENDING)
        .add_columns(GameInstance.created_at, GameInstance.id)
        .offset(offset).limit(limit)
    )
    game = result.scalars().all()

    _game = None
    if not game:
        # create a new game
        game_inst, _game = await generate_game(db)

    if _game:
        data = [{
            "id": game_inst.id,
            "name": _game.name,
            "created": game_inst.created_at.timestamp()
        }]
    else:
        data = [{
            "id": g.id,
            "name": g.game.name,
            "created": g.created_at.timestamp()
        } for g in game]

    count_result = await db.execute(
        select(func.count(GameInstance.id))
        .filter(GameInstance.status == GameStatus.PENDING)
    )
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Games(games=data, count=count).model_dump()
    )


@public.get(
    "/game/{game_id}",
    responses={404: {"model": BadResponse}, 200: {"model": GameInstanceModel}}
)
async def read_game(game_id: int, db: AsyncSession = Depends(get_db)):
    """
    Получение доп. информации по игре
    """
    result = await db.execute(
        select(GameInstance)
        .options(joinedload(GameInstance.game))
        .filter(GameInstance.id == game_id)
    )
    game = result.scalars().first()

    if game is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=BadResponse(message="Game not found").model_dump()
        )

    data = {
        "id": game.id,
        "name": game.game.name,
        "description": game.game.description,
        "game_type": game.game.game_type.value,
        "limit_by_ticket": game.game.limit_by_ticket,
        "min_ticket_count": game.game.min_ticket_count,
        "max_limit_grid": game.game.max_limit_grid,
        "price": float(game.game.price),
        "created": game.created_at.timestamp()
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=GameInstanceModel(**data).model_dump()
    )


@public.post(
    "/game/{game_id}/tickets",
    responses={400: {"model": BadResponse}, 201: {"description": "OK"}}
)
async def buy_tickets(
    game_id: Annotated[int, Path()],
    item: BuyTicket,
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
        Для покупки билетов
    """
    game_inst = await db.execute(
        select(GameInstance)
        .filter(GameInstance.id == game_id)
        .add_columns(GameInstance.status, GameInstance.game_id)
    )
    game_inst = game_inst.scalar()
    if game_inst is None or game_inst.status != GameStatus.PENDING:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Game not found").model_dump()
        )

    game = await db.get(Game, game_inst.game_id)
    if game is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Game not found").model_dump()
        )
    if any(len(n) != game.limit_by_ticket for n in item.numbers):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(
                message=f"Invalid ticket numbers, need {game.limit_by_ticket} per ticket"
            ).model_dump()
        )

    if game.min_ticket_count < len(item.numbers):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(
                message=f"Not enough tickets to participate, need {game.min_ticket_count}"
            ).model_dump()
        )
    if item.demo and len(item.numbers) > 1:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Demo mode is available only for one ticket").model_dump()
        )

    if not item.demo:
        balance_result = await db.execute(
            select(func.sum(Balance.balance))
            .filter(Balance.user_id == user.id)
        )
        total_balance = balance_result.scalar() or 0
        total_price = game.price * len(item.numbers)

        # check if the user has enough balance
        if total_balance < total_price:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(message="Insufficient balance").model_dump()
            )
        # deduct the balance
        await db.execute(
            Balance.__table__.update()
            .where(Balance.user_id == user.id)
            .values(balance=Balance.balance - total_price)
        )
    else:
        # if user already has a demo ticket on this game, use exists()
        ticket = await db.execute(
            select(exists().where(
                Ticket.user_id == user.id,
                Ticket.demo.is_(True),
                Ticket.game_instance_id == game_id
            ))
        )
        if ticket.scalar():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(
                    message="Demo ticket already exists"
                ).model_dump()
            )

    # create ticket
    tickets = [
        Ticket(
            user_id=user.id,
            game_instance_id=game_id,
            numbers=numbers,
            demo=item.demo
        ) for numbers in item.numbers
    ]

    db.add_all(tickets)
    await db.commit()

    # Refresh each ticket individually
    for ticket in tickets:
        await db.refresh(ticket)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content="OK"
    )


@public.get(
    "/tickets",
    responses={400: {"model": BadResponse}, 200: {"model": Tickets}}
)
async def get_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user)],
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение билетов пользователя
    """
    tickets = await db.execute(
        select(Ticket)
        .filter(Ticket.user_id == user.id)
        .offset(skip).limit(limit)
    )
    tickets = tickets.scalars().all()

    data = [{
        "id": t.id,
        "game_instance_id": t.game_instance_id,
        "numbers": t.numbers,
        "demo": t.demo,
        "created": t.created_at.timestamp()
    } for t in tickets]

    count_result = await db.execute(
        select(func.count(Ticket.id))
        .filter(Ticket.user_id == user.id)
    )
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Tickets(tickets=data, count=count).model_dump()
    )
