import datetime
import random
from typing import Annotated
from fastapi import Depends, Path, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, exists
from models.db import get_db
from models.user import Balance, BalanceChangeHistory, User
from models.other import Game, GameInstance, GameStatus, GameType, Ticket
from routers import public
from routers.utils import generate_game, get_user, nth, url_for
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from schemes.base import BadResponse
from schemes.game import (
    BuyTicket,
    EditTicket,
    Games,
    GameInstance as GameInstanceModel,
    Tickets,
    GenTicket,
    TicketMode
)
from schemes.tg import WidgetLogin
from utils.signature import TgAuth
from settings import settings


@public.post("/tg/login", deprecated=True)
async def tg_login(item: WidgetLogin):
    """
        Для логина в telegram mini app через seamless auth
    """
    print(settings.bot_token)
    if not TgAuth(item, settings.bot_token.encode("utf-8")).check_hash():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Bad Request"
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.get(
    "/games", tags=["game"],
    responses={404: {"model": BadResponse}, 200: {"model": Games}}
)
async def game_instances(
    db: Annotated[AsyncSession, Depends(get_db)],
    _type: GameType = GameType.GLOBAL,
    offset: int = 0,
    limit: int = 10
):
    """
    Получение списка доступных игр
    """
    result = await db.execute(
        select(GameInstance)
        .options(joinedload(GameInstance.game).load_only(Game.name))
        .filter(
            GameInstance.status == GameStatus.PENDING,
            GameInstance.game.has(game_type=_type)
        )
        .add_columns(
            GameInstance.created_at,
            GameInstance.id,
            GameInstance.status,
            GameInstance.scheduled_datetime
        )
        .offset(offset).limit(limit)
    )
    game = result.scalars().all()

    _game = None
    if not game:
        # create a new game
        game_inst, _game = await generate_game(db, _type)

    if _game:
        data = [{
            "id": game_inst.id,
            "name": _game.name,
            "image": url_for("static", path=game_inst.image),
            "status": game_inst.status.value,
            "endtime": game_inst.scheduled_datetime.timestamp(),
            "created": game_inst.created_at.timestamp()
        }]
    else:
        data = [{
            "id": g.id,
            "name": g.game.name,
            "image": url_for("static", path=g.image),
            "status": g.status.value,
            "endtime": g.scheduled_datetime.timestamp(),
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
    "/game/{game_id}/calc",
    tags=["game"],
    responses={404: {"model": BadResponse}, 200: {"description": "OK"}}
)
async def calc_balance(
    game_id: Annotated[int, Path()],
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    quantity: int = 1
):
    balance_result = await db.execute(
        select(Balance)
        .filter(Balance.user_id == user.id)
    )
    balance = balance_result.scalar()
    if not balance:
        balance = Balance(user_id=user.id)
        db.add(balance)
        await db.commit()

    result = await db.execute(
        select(GameInstance)
        .options(joinedload(GameInstance.game).load_only(Game.price))
        .filter(GameInstance.id == game_id)
    )
    game = result.scalars().first()

    if game is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=BadResponse(message="Game not found").model_dump()
        )

    total_balance = balance.balance - (game.game.price * quantity)

    return JSONResponse(
        status_code=status.HTTP_200_OK if total_balance >= 0 else status.HTTP_400_BAD_REQUEST,
        content="OK" if total_balance >= 0 else "Insufficient balance"
    )


@public.get(
    "/game/{game_id}", tags=["game"],
    responses={404: {"model": BadResponse}, 200: {"model": GameInstanceModel}}
)
async def read_game(
    game_id: Annotated[int, Path()],
    db: Annotated[AsyncSession, Depends(get_db)]
):
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
        "status": game.status.value,
        "image": url_for("static", path=game.image),
        "game_type": game.game.game_type.value,
        "limit_by_ticket": game.game.limit_by_ticket,
        "min_ticket_count": game.game.min_ticket_count,
        "max_limit_grid": game.game.max_limit_grid,
        "price": float(game.game.price),
        "endtime": g.scheduled_datetime.timestamp(),
        "created": game.created_at.timestamp()
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=GameInstanceModel(**data).model_dump()
    )


@public.post(
    "/game/{game_id}/tickets", tags=["game"],
    responses={400: {"model": BadResponse}, 201: {"description": "OK"}}
)
async def buy_tickets(
    game_id: Annotated[int, Path()],
    item: BuyTicket,
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Для покупки билетов frame:20
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

    if game.min_ticket_count > len(item.numbers):
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
            select(Balance)
            .with_for_update()
            .filter(Balance.user_id == user.id)
        )
        user_balance = balance_result.scalar() or Balance(balance=0)
        total_price = game.price * len(item.numbers)

        # check if the user has enough balance
        if user_balance.balance < total_price:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(message="Insufficient balance").model_dump()
            )
        # deduct the balance and log in balance change history
        user_balance.balance -= total_price
        balance_change = BalanceChangeHistory(
            user_id=user.id,
            change_amount=-total_price,
            change_type="ticket purchase",
            previous_balance=user_balance.balance + total_price,
            new_balance=user_balance.balance
        )
        db.add(balance_change)
        await db.commit()
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


@public.put(
    "/game/{game_id}/tickets", tags=["game"],
    responses={400: {"model": BadResponse}, 200: {"model": Tickets}}
)
async def gen_tickets(
    game_id: Annotated[int, Path()],
    item: Annotated[GenTicket, Depends(GenTicket)],
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    generate tickets
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

    tickets = []

    if item.mode == TicketMode.AUTO:
        count = 1
        while len(tickets) < item.quantity:
            numbers = random.sample(range(1, game.max_limit_grid + 1), game.limit_by_ticket)

            if len(set(numbers)) != game.limit_by_ticket:
                continue

            tickets.append(
                dict(
                    id=count,
                    user_id=user.id,
                    game_instance_id=game_id,
                    won=False,
                    numbers=numbers,
                    demo=False,
                    created=datetime.datetime.utcnow().timestamp()
                )
            )
            count += 1

    if item.mode == TicketMode.MANUAL:
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

        tickets = [
            dict(
                id=i,
                user_id=user.id,
                game_instance_id=game_id,
                numbers=numbers,
                demo=False,
                won=False,
                created=datetime.datetime.utcnow().timestamp()
            ) for i, numbers in enumerate(item.numbers)
        ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Tickets(tickets=tickets, count=item.quantity).model_dump()
    )


@public.patch(
    "/game/{game_id}/tickets/{ticket_id}", tags=["game"],
    responses={400: {"model": BadResponse}, 200: {"model": Tickets}}
)
async def edit_ticket(
    ticket_id: Annotated[int, Path()],
    game_id: Annotated[int, Path()],
    item: EditTicket,
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
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

    if len(item.edited_numbers) != game.limit_by_ticket:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(
                message=f"Invalid ticket numbers, need {game.limit_by_ticket} per ticket"
            ).model_dump()
        )

    ticket = nth(item.numbers, ticket_id - 1, None)
    if not ticket:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Ticket not found").model_dump()
        )

    item.numbers[ticket_id - 1] = item.edited_numbers
    tickets = [
        dict(
            id=i,
            user_id=user.id,
            game_instance_id=game_id,
            numbers=numbers,
            demo=False,
            won=False,
            created=datetime.datetime.utcnow().timestamp()
        ) for i, numbers in enumerate(item.numbers)
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Tickets(tickets=tickets, count=len(item.numbers)).model_dump()
    )


@public.get(
    "/game/{game_id}/leaderboard", tags=["game"],
    responses={400: {"model": BadResponse}, 200: {"model": Tickets}}
)
async def get_leaderboard(
    game_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение лидерборда по игре
    """
    tickets = await db.execute(
        select(Ticket)
        .filter(Ticket.game_instance_id == game_id)
        .order_by(Ticket.won.desc())
        .offset(skip).limit(limit)
    )
    tickets = tickets.scalars().all()

    data = [{
        "id": t.id,
        "game_instance_id": t.game_instance_id,
        "numbers": t.numbers,
        "demo": t.demo,
        "won": t.won,
        "amount": float(t.amount) if t.amount is not None else 0,
        "created": t.created_at.timestamp()
    } for t in tickets]

    count_result = await db.execute(
        select(func.count(Ticket.id))
        .filter(Ticket.game_instance_id == game_id)
    )
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Tickets(tickets=data, count=count).model_dump()
    )
