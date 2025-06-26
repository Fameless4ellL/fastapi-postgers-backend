import datetime
import json
import mimetypes
import random
from contextlib import suppress
from decimal import Decimal, DecimalException
from typing import Annotated, Optional
from fastapi import Depends, Path, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select

from src.exceptions.game import GameExceptions
from src.globals import aredis, storage
from src.models.db import get_db
from src.models.log import Action
from src.models.user import Balance, BalanceChangeHistory, User, Wallet
from src.models.other import (
    Currency,
    Game,
    GameStatus,
    GameType,
    Jackpot,
    Ticket,
    JackpotType,
    GameView,
)
from src.routers import public
from src.utils.dependencies import get_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from src.schemes import BadResponse
from src.schemes import (
    BuyTicket,
    EditTicket,
    Games,
    GameInstance as GameInstanceModel,
    Tickets,
    GenTicket,
    TicketMode,
    Jackpot as JackpotModel,
)
from src.schemes import WidgetLogin
from src.utils.signature import TgAuth
from settings import settings
from src.utils.web3 import transfer


@public.post("/tg/login", deprecated=True)
async def tg_login(item: WidgetLogin):
    """
        Для логина в telegram mini app через seamless auth
    """
    if not TgAuth(item, settings.bot_token.encode("utf-8")).check_hash():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Bad Request"
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.get("/file/games")
def get_file(path: str):
    response = None
    try:
        response = storage.get_object("games", path)
        data = response.data
        content_type, _ = mimetypes.guess_type(path)

    except Exception:
        return Response(status_code=404, content="Image not found")
    finally:
        if response:
            response.close()
            response.release_conn()

    return Response(
        content=data,
        media_type=content_type or "application/octet-stream"
    )


@public.get(
    "/games",
    tags=["game"],
    responses={200: {"model": Games}}
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
    ).options(
        joinedload(Game.currency)
    ).order_by(
        Game.scheduled_datetime.asc()
    )

    if _type is GameType.LOCAL:
        stmt = stmt.filter(Game.country == user.country)

    result = await db.execute(stmt.offset(offset).limit(limit))
    game = result.scalars().all()

    data = [{
        "id": g.id,
        "name": g.name,
        "image": g.image,
        "currency": g.currency.code if g.currency else None,
        "status": g.status.value,
        "price": float(g.price),
        "prize": float(g.prize) if g.prize.isnumeric() else g.prize,
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

    return Games(games=data, count=count)


@public.get(
    "/game/{game_id}/calc",
    tags=["game"],
    responses={200: {"description": "OK"}}
)
async def calc_balance(
    game_id: Annotated[int, Path()],
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    quantity: int = 1
):
    result = await db.execute(
        select(Game)
        .filter(Game.id == game_id)
    )
    game = result.scalars().first()
    await GameExceptions.raise_exception_game_not_found(game)

    stmt = select(Balance).filter(
        Balance.user_id == user.id,
        Balance.currency_id == game.currency_id
    )
    balance_result = await db.execute(stmt)
    balance = balance_result.scalar()

    if not balance:
        balance = Balance(user_id=user.id)
        db.add(balance)
        await db.commit()

    total_balance = balance.balance - (game.price * quantity)

    return JSONResponse(
        status_code=status.HTTP_200_OK if total_balance >= 0 else status.HTTP_400_BAD_REQUEST,
        content="OK" if total_balance >= 0 else "Insufficient balance"
    )


@public.get(
    "/game/{game_id}", tags=["game"],
    responses={200: {"model": GameInstanceModel}}
)
async def read_game(
    user: Annotated[User, Depends(get_user)],
    game_id: Annotated[int, Path()],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """
    Получение доп. информации по игре
    """
    stmt = select(Game).filter(
        Game.id == game_id
    ).options(
        joinedload(Game.currency)
    )

    result = await db.execute(stmt)
    game = result.scalars().first()
    await GameExceptions.raise_exception_game_not_found(game)
    await GameExceptions.raise_exception_on_local_game(game)

    data = {
        "id": game.id,
        "name": game.name,
        "description": game.description,
        "currency": game.currency.code if game.currency else None,
        "status": game.status.value,
        "image": game.image,
        "game_type": game.game_type,
        "kind": game.kind,
        "limit_by_ticket": game.limit_by_ticket,
        "min_ticket_count": game.min_ticket_count,
        "max_limit_grid": game.max_limit_grid,
        "price": float(game.price or 0),
        "prize": float(game.prize or 0) if game.prize.isnumeric() else game.prize,
        "endtime": game.scheduled_datetime.timestamp(),
        "created": game.created_at.timestamp()
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=GameInstanceModel(**data).model_dump(mode='json')
    )


@public.post(
    "/game/{game_id}/tickets",
    tags=["game", Action.TRANSACTION],
    # dependencies=[Depends(LimitVerifier(OperationType.PURCHASE))],
    responses={201: {"description": "OK"}}
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
    game = await db.execute(
        select(Game)
        .filter(Game.id == game_id)
        .options(
            joinedload(Game.currency).joinedload(Currency.network)
        )
    )

    game: Optional[Game] = game.scalar()
    await GameExceptions.raise_exception_game_not_found(game)
    await GameExceptions.raise_exception_on_local_game(game, user)
    await GameExceptions.raise_exception_on_game_conditions(game, item.numbers)

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
            .filter(
                Balance.user_id == user.id,
                Balance.currency_id == game.currency_id
            )
        )
        user_balance = balance_result.scalar()

        if not user_balance:
            user_balance = Balance(
                user_id=user.id,
                currency_id=game.currency_id
            )
            db.add(user_balance)
            await db.commit()

        total_price = game.price * len(item.numbers)

        # check if the user has enough balance
        if user_balance.balance < total_price:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(message="Insufficient balance").model_dump()
            )

        tx, err = transfer(
            game.currency,
            wallet.private_key,
            total_price,
            settings.address,
        )

        if not tx:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(message=err).model_dump()
            )

        # jackpots
        jackpots = await db.execute(
            select(Jackpot)
            .with_for_update()
            .filter(Jackpot.status == GameStatus.PENDING)
        )
        jackpots = jackpots.scalars().all()

        for jackpot in jackpots:
            if jackpot._type == JackpotType.LOCAL and jackpot.country != user.country:
                continue

            percentage = jackpot.percentage or 10
            amount = jackpot.amount or 0

            jackpot.amount = amount + (total_price * percentage / 100)
            jackpot_id = jackpot.id
            db.add(jackpot)

            break

        # deduct the balance and log in balance change history
        user_balance.balance -= total_price
        balance_change = BalanceChangeHistory(
            user_id=user.id,
            currency_id=game.currency_id,
            balance_id=user_balance.id,
            change_amount=-total_price,
            change_type="ticket purchase",
            game_id=game.id,
            game_type=BalanceChangeHistory.GameInstanceType.GAME,
            count=len(item.numbers),
            previous_balance=user_balance.balance + total_price,
            status=BalanceChangeHistory.Status.SUCCESS,
            new_balance=user_balance.balance,
            proof=tx
        )
        db.add(balance_change)

        if game.kind == GameView.MONETARY and str(game.prize):
            with suppress(DecimalException):
                game.prize = str(Decimal(game.prize) + total_price)
                db.add(game)

        await db.commit()

    # create ticket
    tickets = [
        Ticket(
            user_id=user.id,
            game_id=game_id,
            currency_id=game.currency_id,
            numbers=numbers,
            price=game.price,
            demo=item.demo,
            jackpot_id=jackpot_id,
        ) for numbers in item.numbers
    ]

    db.add_all(tickets)
    await db.commit()
    await aredis.delete(f"BUCKET:TICKETS:{user.id}")

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content="OK"
    )


@public.put(
    "/game/{game_id}/tickets", tags=["game"],
    responses={200: {"model": Tickets}}
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
        .filter(Game.status != GameStatus.PENDING)
    )
    game = game.scalar()
    await GameExceptions.raise_exception_game_not_found(game)

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
        if any(len(set(n)) != game.limit_by_ticket for n in item.numbers):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(
                    message=f"Invalid ticket numbers, need {game.limit_by_ticket} per ticket"
                ).model_dump()
            )
        for numbers in item.numbers:
            if not all(0 < i <= game.max_limit_grid for i in numbers):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=BadResponse(
                        message="Invalid ticket numbers, need proper number based on game settings"
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

    await aredis.set(f"BUCKET:TICKETS:{user.id}", json.dumps(tickets), ex=3600*24)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Tickets(tickets=tickets, count=item.quantity).model_dump()
    )


@public.patch(
    "/game/{game_id}/tickets/{ticket_id}", tags=["game"],
    responses={200: {"model": Tickets}}
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
        .filter(Game.status != GameStatus.PENDING)
    )
    game = game.scalar()
    await GameExceptions.raise_exception_game_not_found(game)

    if len(set(item.edited_numbers)) != game.limit_by_ticket:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(
                message=f"Invalid ticket numbers, need {game.limit_by_ticket} per ticket"
            ).model_dump()
        )
    if not all(0 < i <= game.max_limit_grid for i in item.edited_numbers):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(
                message="Invalid ticket numbers, need proper number based on game settings"
            ).model_dump()
        )

    tickets = await aredis.get(f"BUCKET:TICKETS:{user.id}")
    if not tickets:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(
                message="Please generate new tickets"
            ).model_dump()
        )
    tickets = json.loads(tickets.decode("utf-8"))

    for _ticket in tickets:
        if _ticket['id'] == ticket_id:
            _ticket['numbers'] = item.edited_numbers

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Tickets(tickets=tickets, count=len(item.numbers)).model_dump()
    )


@public.get(
    "/game/{game_id}/leaderboard", tags=["game"],
    responses={200: {"model": Tickets}}
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
        .options(joinedload(Ticket.currency))
        .order_by(Ticket.won.desc())
        .offset(skip).limit(limit)
    )
    tickets = tickets.scalars().all()

    data = [{
        "id": t.id,
        "game_instance_id": t.game_id,
        "currency": t.currency.code if t.currency else None,
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
    "/jackpots",
    tags=["Jackpot"],
    responses={200: {"model": JackpotModel}}
)
async def get_jackpots(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение списка джекпотов
    """
    stmt = select(
        func.sum(Ticket.amount).label("total_tickets"),
        Jackpot.id,
        Jackpot.status,
        Jackpot.image,
        Jackpot.scheduled_datetime,
        Jackpot.percentage,
        Jackpot.created_at,
    ).outerjoin(Ticket, Ticket.jackpot_id == Jackpot.id).filter(
        Jackpot.status == GameStatus.PENDING,
        Jackpot._type == JackpotType.LOCAL,
        Jackpot.country == user.country
    ).group_by(Jackpot.id).offset(0).limit(5)
    local = await db.execute(stmt)
    local = local.fetchall() or []

    stmt = select(
        func.sum(Ticket.amount).label("total_tickets"),
        Jackpot.id,
        Jackpot.status,
        Jackpot.image,
        Jackpot.scheduled_datetime,
        Jackpot.percentage,
        Jackpot.created_at,
    ).outerjoin(Ticket, Ticket.jackpot_id == Jackpot.id).filter(
        Jackpot.status == GameStatus.PENDING,
        Jackpot._type == JackpotType.GLOBAL,
    ).group_by(Jackpot.id).offset(0).limit(5)
    global_ = await db.execute(stmt)
    global_ = global_.fetchall() or []

    data = [
        {
            "id": j.id,
            "status": j.status.value,
            "endtime": j.scheduled_datetime.timestamp(),
            "image": j.image,
            "amount": float(j.total_tickets or 0),
            "percentage": float(j.percentage),
            "created": j.created_at.timestamp()
        } for j in local + global_
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )
