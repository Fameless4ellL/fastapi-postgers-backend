import datetime
import json
from typing import Annotated
from fastapi import Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.models import OperationType
from src.models.db import get_sync_db
from src.models.log import Action
from src.models.user import Balance, BalanceChangeHistory, User, Wallet
from src.models.other import (
    Currency,
    InstaBingo,
    TicketStatus,
    Ticket,
    Number
)
from src.routers import public
from src.utils.dependencies import get_user, LimitVerifier
from src.schemes import BadResponse
from src.schemes import BuyInstaTicket
from src.schemes.instabingo import InstaBingoInfo, InstaBingoResults
from settings import settings
from src.utils.workers import deposit, withdraw
from src.utils.rng import get_random


@public.get(
    "/instabingo",
    tags=["InstaBingo"],
    responses={
        404: {"model": BadResponse},
        200: {"model": InstaBingoInfo}
    },
)
async def get_instabingo(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[Session, Depends(get_sync_db)],
):
    """
    Получение нужной информации для игры в инстабинго
    """
    game = db.query(InstaBingo).filter(
        InstaBingo.country == user.country
    ).first()

    if not game:
        game = db.query(InstaBingo).filter(
            InstaBingo.country.is_(None),
        ).first()

        if game is None:
            currency = db.query(Currency).first()
            if not currency:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=BadResponse(message="Currency not found").model_dump()
                )

            game = InstaBingo(
                currency_id=currency.id,
                country=None
            )
            db.add(game)
            db.commit()

            game = db.query(InstaBingo).filter(
                InstaBingo.country.is_(None),
            ).first()

    data = {
        "id": game.id,
        "price": game.price,
        "currency": game.currency.code if game.currency else "",
        "winnings": game.winnings,
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=InstaBingoInfo(**data).model_dump(mode="json")
    )


@public.put(
    "/instabingo/{game_id}/check", tags=["game"],
    responses={
        400: {"model": BadResponse},
    }
)
async def instabingo_check(
    item: BuyInstaTicket,
    user: Annotated[User, Depends(get_user)],
    db: Annotated[Session, Depends(get_sync_db)],
):
    """
    generate tickets
    """
    if len(set(item.numbers)) != 15:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Invalid numbers, should be 15").model_dump()
        )

    stmt = db.query(InstaBingo).filter(
        InstaBingo.country == user.country,
        InstaBingo.deleted.is_(False)
    )

    game = stmt.first()

    if game is None:
        game = db.query(InstaBingo).filter(
            InstaBingo.country.is_(None),
        ).first()

        if game is None:
            currency = db.query(Currency).first()
            if not currency:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=BadResponse(message="Currency not found").model_dump()
                )

            game = InstaBingo(
                currency_id=currency.id,
                country=None
            )
            db.add(game)
            db.commit()

            game = db.query(InstaBingo).filter(
                InstaBingo.country.is_(None),
            ).first()

    if not game:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Game not found").model_dump()
        )

    tickets = [
        dict(
            id=i,
            user_id=user.id,
            instabingo_id=game.id,
            numbers=numbers,
            won=False,
            created=datetime.datetime.now().timestamp()
        ) for i, numbers in enumerate(item.numbers)
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=dict(tickets=tickets, count=item.quantity)
    )


@public.post(
    "/instabingo/tickets",
    tags=["InstaBingo", Action.TRANSACTION],
    dependencies=[Depends(LimitVerifier(OperationType.PURCHASE))],
    responses={400: {"model": BadResponse}, 201: {"description": "OK"}}
)
async def buy_tickets(
    item: BuyInstaTicket,
    user: Annotated[User, Depends(get_user)],
    db: Annotated[Session, Depends(get_sync_db)],
):
    """
    Для покупки билетов frame:20
    """
    stmt = db.query(InstaBingo).filter(
        InstaBingo.country == user.country,
        InstaBingo.deleted.is_(False)
    )

    game = stmt.first()

    if game is None:
        game = db.query(InstaBingo).filter(
            InstaBingo.country.is_(None),
        ).first()

        if game is None:
            currency = db.query(Currency).first()
            if not currency:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=BadResponse(message="Currency not found").model_dump()
                )

            game = InstaBingo(
                currency_id=currency.id,
                country=None
            )
            db.add(game)
            db.commit()

            game = db.query(InstaBingo).filter(
                InstaBingo.country.is_(None),
            ).first()

    if not game:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Game not found").model_dump()
        )

    jackpot_id = None

    wallet = db.query(Wallet).filter(User.id == user.id).first()

    if wallet is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Wallet not found").model_dump()
        )

    user_balance = db.query(
        Balance
    ).with_for_update().filter(
        Balance.user_id == user.id,
        Balance.currency_id == game.currency_id
    ).first()

    if not user_balance:
        user_balance = Balance(
            user_id=user.id,
            currency_id=game.currency_id
        )
        db.add(user_balance)
        db.commit()

    total_price = game.price * len(item.numbers)

    # check if the user has enough balance
    if user_balance.balance < total_price:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=BadResponse(message="Insufficient balance").model_dump()
        )

    win_numbers = []
    generated_numbers = set()
    while len(generated_numbers) < 40:
        start_date = datetime.datetime.now()
        number = await get_random(1, 90)

        if number is None:
            continue

        end_date = datetime.datetime.now()

        if len(win_numbers) >= 15 and set(item.numbers).issubset(generated_numbers):
            break

        if number in generated_numbers:
            continue

        generated_numbers.add(number)
        win_numbers.append((number, start_date, end_date))

    won = False
    prize = 0
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
        user_balance.balance -= game.price
        balance_change = BalanceChangeHistory(
            user_id=user.id,
            currency_id=game.currency_id,
            balance_id=user_balance.id,
            change_amount=-game.price,
            change_type="ticket purchase",
            game_id=game.id,
            game_type=BalanceChangeHistory.GameInstanceType.INSTABINGO,
            count=len(item.numbers),
            previous_balance=user_balance.balance + game.price,
            status=BalanceChangeHistory.Status.PENDING,
            args=json.dumps({"address": settings.address}),
            new_balance=user_balance.balance,
        )
        db.add(balance_change)
        db.commit()
        db.refresh(balance_change)

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
            change_amount=total_price,
            game_id=game.id,
            game_type=BalanceChangeHistory.GameInstanceType.INSTABINGO,
            count=len(item.numbers),
            change_type="won",
            previous_balance=user_balance.balance + total_price,
            status=BalanceChangeHistory.Status.PENDING,
            new_balance=user_balance.balance,
        )
        db.add(balance_change)
        db.commit()
        db.refresh(balance_change)

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
        amount=prize,
        jackpot_id=jackpot_id,
        status=TicketStatus.COMPLETED
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    for number, start_date, end_date in win_numbers:
        number = Number(
            number=number,
            ticket_id=ticket.id,
            start_date=start_date,
            end_date=end_date
        )
        db.add(number)
    db.commit()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=InstaBingoResults(**{
            "won": won,
            "gen": [number for number, _, _, in win_numbers],
            "won_amount": ticket.amount,
            "winnings": game.winnings,
            "numbers": item.numbers
        }).model_dump(mode="json")
    )
