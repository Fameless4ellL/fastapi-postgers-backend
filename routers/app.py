import datetime
import json
import random
from typing import Annotated, Optional
from fastapi import Depends, Path, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, exists
from web3 import AsyncWeb3
from models.db import get_db
from models.user import Balance, BalanceChangeHistory, User, Wallet
from models.other import (
    Currency,
    Game,
    GameStatus,
    GameType,
    Jackpot,
    Ticket,
    JackpotType,
    JackpotStatus,
)
from routers import public
from routers.utils import generate_game, get_currency, get_user, get_w3, nth, url_for
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
    TicketMode,
    Jackpot as JackpotModel,
)
from schemes.tg import WidgetLogin
from utils.signature import TgAuth
from globals import aredis
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
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _type: GameType = GameType.GLOBAL,
    offset: int = 0,
    limit: int = 10
):
    """
    Получение списка доступных игр
    """
    stmt = select(Game).filter(
        Game.status == GameStatus.PENDING,
        Game.game_type == _type
    ).add_columns(
        Game.name,
        Game.price,
        Game.prize,
        Game.max_limit_grid,
        Game.created_at,
        Game.id,
        Game.status,
        Game.scheduled_datetime
    ).offset(offset).limit(limit)

    if _type is GameType.LOCAL:
        stmt = stmt.filter(Game.country == user.country)

    result = await db.execute(stmt)
    game = result.scalars().all()

    data = [{
        "id": g.id,
        "name": g.name,
        "image": url_for("static", path=g.image),
        "status": g.status.value,
        "price": float(g.price),
        "prize": float(g.prize),
        "max_limit_grid": g.max_limit_grid,
        "endtime": g.scheduled_datetime.timestamp(),
        "created": g.created_at.timestamp()
    } for g in game]

    stmt = select(func.count(Game.id)).filter(
        Game.status == GameStatus.PENDING,
        Game.game_type == _type
    )

    if _type is GameType.LOCAL:
        stmt = stmt.filter(Game.country == user.country)

    count_result = await db.execute(stmt)
    count = count_result.scalar()

    if not data and count == 0:
        # create a new game
        _game = await generate_game(db, _type, user.country)

        data = [{
            "id": _game.id,
            "name": _game.name,
            "image": url_for("static", path=_game.image),
            "status": _game.status.value,
            "price": float(_game.price),
            "prize": float(_game.prize),
            "max_limit_grid": _game.max_limit_grid,
            "endtime": _game.scheduled_datetime.timestamp(),
            "created": _game.created_at.timestamp()
        }]

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
        select(Game)
        .filter(Game.id == game_id)
    )
    game = result.scalars().first()

    if game is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=BadResponse(message="Game not found").model_dump()
        )

    total_balance = balance.balance - (game.price * quantity)

    return JSONResponse(
        status_code=status.HTTP_200_OK if total_balance >= 0 else status.HTTP_400_BAD_REQUEST,
        content="OK" if total_balance >= 0 else "Insufficient balance"
    )


@public.get(
    "/game/{game_id}", tags=["game"],
    responses={404: {"model": BadResponse}, 200: {"model": GameInstanceModel}}
)
async def read_game(
    user: Annotated[User, Depends(get_user)],
    game_id: Annotated[int, Path()],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Получение доп. информации по игре
    """
    result = await db.execute(
        select(Game)
        .filter(Game.id == game_id)
    )
    game = result.scalars().first()

    if game is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=BadResponse(message="Game not found").model_dump()
        )
    if (
        game.game_type == GameType.LOCAL
        and str(game.country) != user.country
    ):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=BadResponse(message="Game not found").model_dump()
        )

    data = {
        "id": game.id,
        "name": game.name,
        "description": game.description,
        "status": game.status.value,
        "image": url_for("static", path=game.image),
        "game_type": game.game_type.value,
        "limit_by_ticket": game.limit_by_ticket,
        "min_ticket_count": game.min_ticket_count,
        "max_limit_grid": game.max_limit_grid,
        "price": float(game.price or 0),
        "prize": float(game.prize or 0),
        "endtime": game.scheduled_datetime.timestamp(),
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
    currency: Annotated[Currency, Depends(get_currency)],
    w3: Annotated[AsyncWeb3, Depends(get_w3)],
):
    """
    Для покупки билетов frame:20
    """
    game = await db.execute(
        select(Game)
        .filter(Game.id == game_id)
    )
    game: Optional[Game] = game.scalar()

    if game is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Game not found").model_dump()
        )

    if (
        game.game_type == GameType.LOCAL
        and str(game.country) != user.country
    ):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
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

    jackpot_id = None

    if not item.demo:
        wallet = await db.execute(
            select(Wallet).filter(User.id == user.id)
        )
        wallet = wallet.scalar()

        if wallet is None:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(message="Wallet not found").model_dump()
            )

        balance_result = await db.execute(
            select(Balance)
            .with_for_update()
            .filter(Balance.user_id == user.id)
        )
        user_balance = balance_result.scalar() or Balance(balance=0)
        total_price = game.price * len(item.numbers)

        try:
            contract = w3.eth.contract(
                address=currency.address,
                abi=json.loads(await aredis.get("abi"))
            )
            amount = int(total_price * 10 ** currency.decimals)

            w3.eth.default_account = wallet.address
            _hash = await contract.functions.transfer(settings.address, amount).transact()
            tx = await w3.eth.wait_for_transaction_receipt(_hash, timeout=60)

            if tx is None or tx.status != 1:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=BadResponse(message="Transaction failed").model_dump()
                )
        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(message=str(e)).model_dump()
            )

        # jackpots
        jackpots = await db.execute(
            select(Jackpot)
            .filter(
                Jackpot.status == JackpotStatus.PENDING
            )
        )
        jackpots = jackpots.scalars().all()

        for jackpot in jackpots:
            if jackpot._type == JackpotType.LOCAL and jackpot.country != user.country:
                continue

            jackpot.amount += total_price * float(jackpot.percentage) / 100
            jackpot_id = jackpot.id
            db.add(jackpot)

            break

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
                Ticket.game_id == game_id
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
            game_id=game_id,
            numbers=numbers,
            demo=item.demo,
            jackpot_id=jackpot_id,
        ) for numbers in item.numbers
    ]

    db.add_all(tickets)
    await db.commit()

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
    game = await db.execute(
        select(Game)
        .filter(Game.id == game_id)
    )
    game = game.scalar()
    if game is None or game.status != GameStatus.PENDING:
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
    game = await db.execute(
        select(Game)
        .filter(Game.id == game_id)
    )
    game = game.scalar()
    if game is None or game.status != GameStatus.PENDING:
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
        .filter(Ticket.game_id == game_id)
        .order_by(Ticket.won.desc())
        .offset(skip).limit(limit)
    )
    tickets = tickets.scalars().all()

    data = [{
        "id": t.id,
        "game_instance_id": t.game_id,
        "numbers": t.numbers,
        "demo": t.demo,
        "won": t.won,
        "amount": float(t.amount) if t.amount is not None else 0,
        "created": t.created_at.timestamp()
    } for t in tickets]

    count_result = await db.execute(
        select(func.count(Ticket.id))
        .filter(Ticket.game_id == game_id)
    )
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Tickets(tickets=data, count=count).model_dump()
    )


@public.get(
    "/jackpots", tags=["Jackpot"],
    responses={400: {"model": BadResponse}, 200: {"model": JackpotModel}}
)
async def get_jackpots(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение списка джекпотов
    """
    stmt = select(Jackpot).filter(
        Jackpot.status == GameStatus.PENDING,
        Jackpot._type == JackpotType.LOCAL,
        Jackpot.country == user.country
    ).offset(0).limit(5)
    local = await db.execute(stmt)
    local = local.scalars().all() or []

    stmt = select(Jackpot).filter(
        Jackpot.status == GameStatus.PENDING,
        Jackpot._type == JackpotType.GLOBAL
    ).offset(0).limit(5)
    global_ = await db.execute(stmt)
    global_ = global_.scalars().all() or []

    data = [
        {
            "id": j.id,
            "status": j.status.value,
            "endtime": j.scheduled_datetime.timestamp(),
            "created": j.created_at.timestamp()
        } for j in local + global_
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )
