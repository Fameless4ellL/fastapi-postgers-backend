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
    Ticket,
)
from routers import public
from routers.utils import get_user
from sqlalchemy.ext.asyncio import AsyncSession
from schemes.base import BadResponse
from schemes.game import BuyInstaTicket
from schemes.instabingo import InstaBingoInfo
from settings import settings
from utils.web3 import transfer


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
        InstaBingo.prize,
        Currency.code
    ).join(
        Currency, InstaBingo.currency_id == Currency.id
    ).where(
        InstaBingo.country == user.country
    )
    data = await db.execute(stmt)
    data = data.scalar()

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
    game = await db.execute(
        select(
            Currency.code.label("currency"),
            InstaBingo
        )
        .join(
            Currency, InstaBingo.currency_id == Currency.id
        )
    )
    game = game.scalar()

    if game is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Game not found").model_dump()
        )

    if any(len(n) != 15 for n in item.numbers):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(
                message=(
                    f"Invalid ticket numbers, "
                    f"need {15} for ticket"
                )
            ).model_dump()
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

    # deduct the balance and log in balance change history
    user_balance.balance -= total_price
    balance_change = BalanceChangeHistory(
        user_id=user.id,
        currency_id=game.currency_id,
        balance_id=user_balance.id,
        change_amount=-total_price,
        change_type="ticket purchase",
        previous_balance=user_balance.balance + total_price,
        status=BalanceChangeHistory.Status.SUCCESS,
        new_balance=user_balance.balance,
        proof=tx
    )
    db.add(balance_change)
    await db.commit()

    # create ticket
    tickets = [
        Ticket(
            user_id=user.id,
            instabingo_id=game.id,
            numbers=numbers,
            jackpot_id=jackpot_id,
        ) for numbers in item.numbers
    ]

    db.add_all(tickets)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content="OK"
    )
