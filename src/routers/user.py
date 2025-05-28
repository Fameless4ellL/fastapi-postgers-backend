import importlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, List

import pycountry
from eth_account import Account
from eth_account.signers.local import LocalAccount
from fastapi import Depends, Query, status, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from tronpy.keys import to_base58check_address

from src.globals import aredis, q
from src.models.db import get_db
from src.models.log import Action
from src.models.other import Currency, GameStatus, Ticket, InstaBingo, Jackpot, Game
from src.models.user import (
    Balance,
    Kyc,
    Notification,
    User,
    Wallet,
    BalanceChangeHistory,
    Document
)
from src.routers import public
from src.utils.dependencies import get_user, get_currency, get_user_token, worker
from src.utils.validators import url_for
from src.schemes import BadResponse, Country, JsonForm
from src.schemes import (
    MyGames, MyGamesType, Tickets, Withdraw
)
from src.schemes import KYC, Notifications, Profile, UserBalance, Usersettings, Transactions


@public.get(
    "/profile",
    tags=["user"],
    responses={
        400: {"model": BadResponse},
        200: {"model": Profile}
    }
)
async def profile(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение информации о пользователе
    """

    # sum balances
    balances = await db.execute(
        select(func.sum(Balance.balance))
        .filter(Balance.user_id == user.id)
    )
    balance = float(balances.scalar() or 0)

    wallet_result = await db.execute(
        select(Wallet)
        .filter(Wallet.user_id == user.id)
    )
    wallet = wallet_result.scalar()
    if not wallet:
        acc: LocalAccount = Account.create()

        wallet = Wallet(
            user_id=user.id,
            address=acc.address,
            private_key=acc.key.hex()
        )
        db.add(wallet)
        await db.commit()

        await aredis.sadd("BLOCKER:WALLETS", wallet.address)

    data = None
    document = await db.execute(
        select(Document)
        .filter(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
    )
    document = document.scalar()

    if document:
        data = {
            "first_name": user.firstname,
            "patronomic": user.patronomic,
            "last_name": user.lastname,
            "document": url_for("static/kyc", path=document.file.name),
        }

    notifications = await db.execute(
        select(exists().where(
            Notification.user_id == user.id,
            Notification.read.is_(False)
        ))
    )
    notifications = notifications.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Profile(
            balance=balance,
            kyc=data,
            locale=user.language_code or "EN",
            address={
                "base58": to_base58check_address(wallet.address),
                "evm": wallet.address,
            },
            notifications=notifications,
            country=user.country or "USA",
            username=user.username
        ).model_dump()
    )


@public.get(
    "/balance",
    tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": List[UserBalance]}}
)
async def balance(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение balance пользователя
    """

    balancies = await db.execute(
        select(Balance).options(
            joinedload(Balance.currency).joinedload(Currency.network)
        )
        .filter(Balance.user_id == user.id)
    )
    balance = balancies.scalars().all()

    if not balance:
        currencies = await db.execute(select(Currency))
        for currency in currencies.scalars().all():
            bal = Balance(
                user_id=user.id,
                currency_id=currency.id,
            )
            db.add(bal)
        await db.commit()

        balancies = await db.execute(
            select(Balance).options(
                joinedload(Balance.currency).joinedload(Currency.network)
            )
            .filter(Balance.user_id == user.id)
        )
        balance = balancies.scalars().all()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=[UserBalance(
            network=b.currency.network.symbol,
            currency=b.currency.code,
            balance=float(b.balance)
        ).model_dump() for b in balance]
    )


@public.post("/withdraw", tags=["user", Action.WITHDRAW])
async def withdraw(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    currency: Annotated[Currency, Depends(get_currency)],
    item: Withdraw
):
    """
    Вывод средств
    """
    # check kyc status
    stmt = select(Kyc).filter(Kyc.country == user.country)
    kyc = await db.execute(stmt)
    kyc = kyc.scalar()
    if kyc and not user.kyc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="KYC required"
        )

    wallet_result = await db.execute(
        select(Wallet)
        .filter(Wallet.user_id == user.id)
    )
    wallet = wallet_result.scalar()

    if not wallet:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Wallet not found"
        )

    balance_result = await db.execute(
        select(Balance)
        .with_for_update()
        .filter(
            Balance.user_id == user.id,
            Balance.currency_id == currency.id
        )
    )
    balance = balance_result.scalar()
    if not balance:
        balance = Balance(user_id=user.id)
        db.add(balance)

    if balance.balance < item.amount:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Insufficient funds"
        )

    history = BalanceChangeHistory(
        user_id=user.id,
        balance_id=balance.id,
        currency_id=currency.id,
        change_amount=item.amount,
        change_type="withdraw",
        status=BalanceChangeHistory.Status.PENDING,
        previous_balance=balance.balance,
        new_balance=balance.balance - Decimal(item.amount),
        args=json.dumps({"address": item.address})
    )

    db.add(history)

    balance.balance = history.new_balance
    db.add(balance)

    await db.commit()

    q.enqueue(
        worker.withdraw,
        history_id=history.id,
        job_id=f"withdraw_{history.id}",
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.post(
    "/upload",
    tags=["user", Action.UPDATE],
    responses={400: {"model": BadResponse}, 200: {"model": str}}
)
async def upload_kyc(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Annotated[KYC, JsonForm()],
    files: List[UploadFile],
    avatar: Annotated[UploadFile, File(include_in_schema=False)] = None
):
    """
    Загрузка документа
    """
    user.firstname = item.first_name
    user.lastname = item.last_name
    user.patronomic = item.patronomic

    if avatar:
        avatar.filename = f"{user.id}_{avatar.filename}"
        user.avatar_v1 = avatar

    db.add(user)

    for file in files:
        if not file.content_type.startswith("image"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content="Invalid file type"
            )

        file.filename = f"{user.id}_{file.filename}"
        doc = Document(
            user_id=user.id,
            file=file
        )
        db.add(doc)

    await db.commit()

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")


@public.get(
    "/tickets", tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": Tickets}}
)
async def get_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user)],
    game_id: int = None,
    jackpot_id: int = None,
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение билетов пользователя
    """
    stmt = select(Ticket).filter(Ticket.user_id == user.id)

    if game_id:
        stmt = stmt.filter(Ticket.game_id == game_id)

    if jackpot_id:
        stmt = stmt.filter(Ticket.jackpot_id == jackpot_id)

    tickets = await db.execute(stmt.offset(skip).limit(limit))
    tickets = tickets.scalars().all()

    data = [{
        "id": t.id,
        "game_instance_id": t.game_id,
        "currency": t.currency.code if t.currency else None,
        "numbers": t.numbers,
        "demo": t.demo,
        "won": t.won,
        "amount": float(t.amount),
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


@public.get(
    "/countries", tags=["settings"],
    responses={400: {"model": BadResponse}, 200: {"model": Country}}
)
async def get_countries(
    q: str = Query('', description="Search query")
):
    """
    Получение список стран
    """
    try:
        if q:
            countries = pycountry.countries.search_fuzzy(q)
        else:
            countries = sorted(pycountry.countries, key=lambda x: x.name)
    except LookupError:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=[]
        )

    excluded_alpha_3 = {
        "ATA",
        "GRL",
        "HKG",
        "PRI",
        "TWN",
        "GIB",
        "BMU",
        "FLK",
        "VAT",
        "ESH",
        "PSE",
    }
    data = [{
        "alpha_3": country.alpha_3,
        "name": country.name,
        "flag": country.flag
    }
        for country in countries
        if country.alpha_3 not in excluded_alpha_3
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )


@public.get(
    "/history", tags=["user"],
    responses={
        400: {"model": BadResponse},
        200: {"model": Transactions}
    }
)
async def get_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user)],
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение истории изменения баланса
    """
    history = await db.execute(
        select(
            BalanceChangeHistory.id,
            BalanceChangeHistory.change_amount,
            BalanceChangeHistory.change_type,
            BalanceChangeHistory.status,
            Currency.code.label("currency"),
            BalanceChangeHistory.created_at,
        )
        .join(Currency, BalanceChangeHistory.currency_id == Currency.id)
        .filter(BalanceChangeHistory.user_id == user.id)
        .order_by(BalanceChangeHistory.created_at.desc())
        .offset(skip).limit(limit)
    )
    history = history.fetchall()

    data = [{
        "id": h.id,
        "amount": h.change_amount,
        "currency": h.currency,
        "type": h.change_type,
        "status": h.status,
        "created": h.created_at.timestamp()
    } for h in history]

    count_result = await db.execute(
        select(func.count(BalanceChangeHistory.id))
        .filter(BalanceChangeHistory.user_id == user.id)
    )
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Transactions(
            items=data,
            count=count
        ).model_dump(mode='json')
    )


@public.get(
    "/mygames", tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": MyGames}}
)
async def get_my_games(
    db: Annotated[AsyncSession, Depends(get_db)],
    # user: Annotated[User, Depends(get_user)],
    item: MyGamesType,
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение игр пользователя в котором он участвовал
    """
    # TODO refactor
    model = importlib.import_module("src.models.other")
    model = getattr(model, item.model)

    if item.model == "InstaBingo":
        stmt = (
            select(
                func.json_build_object(
                    "id", Ticket.id,
                    "price", InstaBingo.price,
                    "won", Ticket.won,
                    "currency", Currency.code,
                    "total_amount", func.sum(Ticket.amount).label("total_amount"),
                    "created", Ticket.created_at,
                    "endtime", Ticket.created_at
                ))
            .select_from(InstaBingo)
            .join(Currency, Currency.id == InstaBingo.currency_id)
            .join(Ticket, Ticket.instabingo_id == InstaBingo.id)
            .group_by(
                Ticket.id,
                InstaBingo.price,
                Ticket.won,
                Currency.code,
                Ticket.created_at
            )
            .order_by(Ticket.created_at.desc())
        )
    elif item.model == "Jackpot":
        stmt = (
            select(
                func.json_build_object(
                    "id", Ticket.id,
                    "currency", Currency.code,
                    "name", Jackpot.name,
                    "image", Jackpot.image,
                    "status", Jackpot.status,
                    "prize", Jackpot.amount,
                    "endtime", Jackpot.scheduled_datetime,
                    "created", Jackpot.created_at,
                ))
            .select_from(Jackpot)
            .join(Currency, Currency.id == Jackpot.currency_id)
            .join(Ticket, Ticket.jackpot_id == Jackpot.id)
            .group_by(
                Ticket.id,
                Ticket.won,
                Currency.code,
                Ticket.created_at,
                Jackpot.name,
                Jackpot.image,
                Jackpot.status,
                Jackpot.amount,
                Jackpot.scheduled_datetime,
                Jackpot.created_at
            )
            .order_by(Ticket.created_at.desc())
        )
    else:
        stmt = (
            select(
                func.json_build_object(
                    "id", Ticket.id,
                    "currency", Currency.code,
                    "name", Game.name,
                    "image", Game.image,
                    "status", Game.status,
                    "price", Game.price,
                    "max_limit_grid", Game.max_limit_grid,
                    "prize", Game.prize,
                    "endtime", Game.scheduled_datetime,
                    "created", Game.created_at,
                ))
            .select_from(Game)
            .join(Currency, Currency.id == Game.currency_id)
            .join(Ticket, Ticket.game_id == Game.id)
            .group_by(
                Ticket.id,
                Game.name,
                Game.image,
                Game.status,
                Game.price,
                Game.max_limit_grid,
                Game.prize,
                Game.scheduled_datetime,
                Game.created_at,
                Ticket.won,
                Currency.code,
                Ticket.created_at
            )
            .order_by(Ticket.created_at.desc())
        )

    count = stmt.with_only_columns(func.count(model.id))
    count = await db.execute(count)
    count = count.scalar() or 0

    stmt = stmt.order_by(Ticket.created_at.desc())
    items = await db.execute(stmt.offset(skip).limit(limit))
    items = items.scalars().fetchall()

    for i in items:
        if item.model == "InstaBingo":
            i["status"] = GameStatus.COMPLETED.name
            i["name"] = "InstaBingo"
        try:
            i["endtime"] = datetime.fromisoformat(i["endtime"]).timestamp()
            i["created"] = datetime.fromisoformat(i["created"]).timestamp()
        except ValueError:
            i["endtime"] = datetime.strptime( i["endtime"], "%Y-%m-%dT%H:%M:%S.%f").timestamp()
            i["created"] = datetime.strptime(i["created"], "%Y-%m-%dT%H:%M:%S.%f").timestamp()
        except Exception:
            pass

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=MyGames(games=items, count=count).model_dump()
    )


@public.get(
    "/notifications", tags=["user"],
    responses={400: {"model": BadResponse}, 200: {"model": Notifications}}
)
async def get_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user_token)],
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение уведомлений для пользователя
    """

    stmt = select(Notification).filter(Notification.user_id == user.id)
    notifications = await db.execute(stmt.offset(skip).limit(limit))
    notifications = notifications.scalars().all()

    data = [{
        "id": n.id,
        "head": n.head,
        "body": n.body,
        "args": json.loads(n.args),
        "created": n.created_at.timestamp()
    } for n in notifications]

    count_stmt = select(func.count(Notification.id)).filter(
        Notification.user_id == user.id
    )
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id)
        .values(read=True)
    )
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=dict(items=data, count=count)
    )


@public.post(
    "/settings", tags=["user", Action.UPDATE],
    responses={400: {"model": BadResponse}, 200: {"model": Notifications}}
)
async def set_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user)],
    item: Usersettings,
):
    """
    Изменение настроек пользователя
    """

    user.language_code = item.locale
    user.country = item.country
    db.add(user)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content="OK"
    )
