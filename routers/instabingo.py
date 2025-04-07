import datetime
import json
import random
from typing import Annotated
from fastapi import Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from models.db import get_db
from models.log import Action
from models.user import Balance, BalanceChangeHistory, User, Wallet
from models.other import (
    Currency,
    InstaBingo,
    TicketStatus,
    Ticket,
    Number
)
from routers import public
from routers.utils import get_user
from sqlalchemy.ext.asyncio import AsyncSession
from schemes.base import BadResponse
from schemes.game import BuyInstaTicket
from schemes.instabingo import InstaBingoInfo
from settings import settings
from utils.workers import deposit, withdraw
from utils.rng import get_random


@public.get(
    "/instabingo", tags=["InstaBingo"],
    responses={404: {"model": BadResponse}, 200: {"model": InstaBingoInfo}},
)
async def get_instabingo(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение нужной информации для игры в инстабинго
    """
    stmt = select(
        InstaBingo.id,
        InstaBingo.price,
        Currency.code
    ).join(
        Currency, InstaBingo.currency_id == Currency.id
    ).where(
        InstaBingo.country == user.country
    )
    data = await db.execute(stmt)
    data = data.fetchall()

    if not data:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=InstaBingoInfo().model_dump()
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=InstaBingoInfo(data).model_dump()
    )


@public.post(
    "/instabingo/tickets",
    tags=["InstaBingo", Action.TRANSACTION],
    responses={400: {"model": BadResponse}, 201: {"description": "OK"}}
)
async def buy_tickets(
    item: BuyInstaTicket,
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Для покупки билетов frame:20
    """
    if len(set(item.numbers)) != 15:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Invalid numbers, should be 15").model_dump()
        )

    game = await db.execute(
        select(
            Currency.code.label("currency"),
            InstaBingo.id,
            InstaBingo.currency_id,
            InstaBingo.winnings,
            InstaBingo.price
        )
        .join(
            Currency, InstaBingo.currency_id == Currency.id
        ).filter(
            InstaBingo.country == user.country,
            InstaBingo.deleted.is_(False)
        )
    )
    game = game.fetchone()

    if game is None:
        currency = await db.execute(
            select(Currency)
        )
        currency = currency.scalar()

        game = InstaBingo(
            currency_id=currency.id,
            country=user.country
        )
        db.add(game)
        await db.commit()

        game = await db.execute(
            select(
                Currency.code.label("currency"),
                InstaBingo.id,
                InstaBingo.currency_id,
                InstaBingo.winnings,
                InstaBingo.price
            )
            .join(
                Currency, InstaBingo.currency_id == Currency.id
            ).filter(
                InstaBingo.country == user.country,
                InstaBingo.deleted.is_(False)
            )
        )
        game = game.fetchone()

    if not game:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Game not found").model_dump()
        )

    jackpot_id = None

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

    win_numbers = []
    while len(win_numbers) < 15:
        start_date = datetime.datetime.now()
        number = get_random(0, 90)
        end_date = datetime.datetime.now()

        if number in win_numbers:
            continue

        win_numbers.append((number, start_date, end_date))

    won = False
    if not game.winnings:
        prize = game.price * 2

    if all(any(num == win_num[0] for win_num in win_numbers) for num in item.numbers):
        last_number = item.numbers[-1]
        prize = next(
            (game.winnings[p] for p in game.winnings.keys() if p >= last_number),
            None
        )
        won = True

        if not prize:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=BadResponse(
                    message="Prize not found"
                ).model_dump()
            )

    if not won:
        user_balance.balance -= total_price
        balance_change = BalanceChangeHistory(
            user_id=user.id,
            currency_id=game.currency_id,
            balance_id=user_balance.id,
            change_amount=-total_price,
            change_type="ticket purchase",
            previous_balance=user_balance.balance + total_price,
            status=BalanceChangeHistory.Status.PENDING,
            args=json.dumps({"address": settings.address}),
            new_balance=user_balance.balance,
        )
        db.add(balance_change)
        await db.commit()
        await db.refresh(balance_change)

        withdraw(
            history_id=balance_change.id,
            change_type=balance_change.change_type
        )

    else:
        user_balance.balance += total_price
        balance_change = BalanceChangeHistory(
            user_id=user.id,
            currency_id=game.currency_id,
            balance_id=user_balance.id,
            change_amount=-total_price,
            change_type="won",
            previous_balance=user_balance.balance + total_price,
            status=BalanceChangeHistory.Status.PENDING,
            new_balance=user_balance.balance,
        )
        db.add(balance_change)
        await db.commit()
        await db.refresh(balance_change)

        deposit(
            history_id=balance_change.id,
            change_type=balance_change.change_type
        )

    # create ticket
    ticket = Ticket(
        user_id=user.id,
        instabingo_id=game.id,
        numbers=item.numbers,
        won=won,
        jackpot_id=jackpot_id,
        status=TicketStatus.COMPLETED
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    for number, start_date, end_date in win_numbers:
        number = Number(
            number=number,
            ticket_id=ticket.id,
            start_date=start_date,
            end_date=end_date
        )
        db.add(number)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"won": won}
    )
