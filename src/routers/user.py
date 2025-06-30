import json
from decimal import Decimal
from typing import Annotated, Union

from eth_account import Account
from eth_account.signers.local import LocalAccount
from fastapi import Depends, status, UploadFile, File, HTTPException, APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import sqltypes
from tronpy.keys import to_base58check_address

from settings import settings
from src.exceptions.base import BadRequestError
from src.globals import aredis, q
from src.models.db import get_db
from src.models.log import Action
from src.models.other import Currency, GameStatus, Ticket, InstaBingo, Jackpot, Game, Network
from src.models.user import (
    Balance,
    Kyc,
    Notification,
    User,
    Wallet,
    BalanceChangeHistory,
    Document
)
from src.schemes import JsonForm, UserBalanceList, KYCProfile
from src.schemes import KYC, Notifications, Profile, Usersettings, Transactions
from src.schemes import (
    MyGames, MyGamesType, Tickets, Withdraw
)
from src.utils import worker
from src.utils.dependencies import get_user, get_currency, Token, JWTBearer

users_router = APIRouter(tags=["v1.public.users"])


@users_router.get(
    "/profile",
    response_model=Profile,
)
async def profile(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение информации о пользователе
    """
    _profile = (
        select(
            func.json_build_object(
                "id", User.id,
                "username", User.username,
                "firstname", User.firstname,
                "lastname", User.lastname,
                "patronomic", User.patronomic,
                "language_code", User.language_code,
                "kyc_approved", User.kyc,
                "country", User.country,
                "telegram", User.telegram,
                "phone_number", User.phone_number,
                "notifications", func.exists(
                    select(Notification.id)
                    .filter(
                        Notification.user_id == User.id,
                        Notification.read.is_(False)
                    ).scalar_subquery()
                ),
                "address", Wallet.address,
                "balance", func.round(func.coalesce(Balance.balance, 0), 2)
            )
        )
        .select_from(User)
        .join(Balance, Balance.user_id == User.id, isouter=True)
        .join(Wallet, Wallet.user_id == User.id, isouter=True)
        .join(Document, Document.user_id == User.id, isouter=True)
        .filter(User.id == user.id)
    )
    _profile = await db.execute(_profile)
    _profile = _profile.scalar()

    if not _profile["address"]:
        acc: LocalAccount = Account.create()

        wallet = Wallet(
            user_id=user.id,
            address=acc.address,
            private_key=acc.key.hex()
        )
        db.add(wallet)
        await db.commit()

        await aredis.sadd("BLOCKER:WALLETS", wallet.address)

        _profile["address"] = wallet.address

    _profile["address"] = {
        "base58": to_base58check_address(_profile["address"]),
        "evm": _profile["address"],
    }

    return _profile


@users_router.get(
    "/kyc",
    response_model=KYCProfile
)
async def get_kyc(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = (
        select(
            Document.id,
            Document.file,
            func.date_part('epoch', Document.created_at).label('epoch')
        )
        .select_from(Document)
        .filter(Document.user_id == user.id)
    )
    data = await db.execute(stmt)
    data = data.fetchall()

    data = {
        "first_name": user.firstname,
        "last_name": user.lastname,
        "patronomic": user.patronomic,
        "documents": [{
            "id": obj.id,
            "file": obj.file,
            "filename": obj.file.name if obj.file else None,
            "created_at": obj.epoch
        } for obj in data]
    }

    return data


@users_router.get(
    "/balance",
    response_model=UserBalanceList
)
async def balance(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Получение balance пользователя
    """

    data = (
        select(
            func.json_build_object(
                "id", Balance.id,
                "balance", Balance.balance,
                "currency", Currency.code,
                "network", Network.symbol
            )
        )
        .select_from(Balance)
        .join(Currency, Balance.currency_id == Currency.id)
        .join(Network, Currency.network_id == Network.id)
        .filter(Balance.user_id == user.id)
    )
    data = await db.execute(data)
    data = data.scalars().all()

    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No balances found")

    return {"items": data}


@users_router.post(
    "/withdraw",
    tags=[Action.WITHDRAW],
    # dependencies=[Depends(LimitVerifier(OperationType.WITHDRAWAL))],
)
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

    if wallet.address == item.address:
        raise BadRequestError("Can't withdraw same address as your wallet")

    balance_result = await db.execute(
        select(Balance)
        .filter(
            Balance.user_id == user.id,
            Balance.currency_id == currency.id
        )
        .with_for_update()
    )
    _balance = balance_result.scalar()
    if not balance:
        _balance = Balance(
            user_id=user.id,
            currency_id=currency.id
        )
        db.add(balance)
        _balance = await db.refresh(_balance)

    if _balance.balance < item.amount:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Insufficient funds"
        )

    history = BalanceChangeHistory(
        user_id=user.id,
        balance_id=_balance.id,
        currency_id=currency.id,
        change_amount=item.amount,
        change_type="withdraw",
        status=BalanceChangeHistory.Status.PENDING,
        previous_balance=_balance.balance,
        new_balance=_balance.balance - Decimal(item.amount),
        args=json.dumps({"address": item.address})
    )

    db.add(history)
    _balance.balance = history.new_balance
    db.add(_balance)

    await db.commit()

    q.enqueue(
        worker.withdraw,
        history_id=history.id,
        job_id=f"withdraw_{history.id}",
    )

    return "OK"


@users_router.post(
    "/upload",
    tags=[Action.UPDATE],
    responses={200: {"model": str}}
)
async def upload_kyc(
    user: Annotated[User, Depends(get_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Annotated[KYC, JsonForm()],
    files: Union[list[UploadFile], None] = None,
    avatar: Annotated[UploadFile, File(include_in_schema=True)] = None
):
    """
    Загрузка документа
    """
    user.firstname = item.first_name
    user.lastname = item.last_name
    user.patronomic = item.patronomic

    if avatar:
        user.avatar_v1 = avatar

    db.add(user)

    await db.execute(
        delete(Document).where(Document.user_id == user.id)
    )

    if files:
        for file in files:
            file.filename = f"{user.id}/{file.filename}"
            doc = Document(user_id=user.id, file=file)
            db.add(doc)

    await db.commit()

    return "OK"


@users_router.get(
    "/tickets",
    responses={200: {"model": Tickets}}
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
    stmt = (
        select(
            func.json_build_object(
                "id", Ticket.id,
                "game_instance_id", Ticket.game_id,
                "currency", Currency.code,
                "numbers", Ticket.numbers,
                "demo", Ticket.demo,
                "won", Ticket.won,
                "amount", Ticket.amount,
                "created", func.extract('epoch', Ticket.created_at)
            )
        )
        .select_from(Ticket)
        .join(Currency, Ticket.currency_id == Currency.id)
        .filter(Ticket.user_id == user.id)
        .order_by(Ticket.created_at.desc())
        .group_by()
    )

    if game_id:
        stmt = stmt.filter(Ticket.game_id == game_id)

    if jackpot_id:
        stmt = stmt.filter(Ticket.jackpot_id == jackpot_id)

    count = stmt.order_by(None).with_only_columns(func.count())
    count = await db.execute(count)
    count = count.scalar()

    tickets = await db.execute(stmt.offset(skip).limit(limit))
    tickets = tickets.scalars().all()

    return Tickets(
        tickets=tickets,
        count=count
    )


@users_router.get(
    "/history",
    responses={200: {"model": Transactions}}
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

    return Transactions(
        items=data,
        count=count
    )


@users_router.get(
    "/mygames",
    responses={200: {"model": MyGames}}
)
async def get_my_games(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_user)],
    item: MyGamesType,
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение игр пользователя в котором он участвовал
    """
    if item.model == "InstaBingo":
        stmt = (
            select(
                func.json_build_object(
                    "id", InstaBingo.id,
                    "game_id", InstaBingo.id,
                    "price", Ticket.price,
                    "won", func.bool_and(Ticket.won),
                    "demo", func.bool_and(Ticket.demo),
                    "currency", Currency.code,
                    "total_amount", Ticket.amount,
                    "ticket_count", func.count(Ticket.id).label("ticket_count"),
                    "endtime", func.date_part('epoch', Ticket.created_at),
                    "created", func.date_part('epoch', Ticket.created_at),
                    "status", func.cast(GameStatus.COMPLETED.name, sqltypes.VARCHAR(50)),
                    "name", func.cast("InstaBingo", sqltypes.VARCHAR(50)),
                ))
            .select_from(InstaBingo)
            .join(Currency, Currency.id == InstaBingo.currency_id)
            .join(Ticket, Ticket.instabingo_id == InstaBingo.id)
            .filter(Ticket.user_id == user.id)
            .group_by(
                InstaBingo.id,
                InstaBingo.price,
                Ticket.id,
                Currency.code
            )
            .order_by(Ticket.created_at.desc())
        )

    elif item.model == "Jackpot":
        stmt = (
            select(
                func.json_build_object(
                    "id", Jackpot.id,
                    "game_id", Jackpot.id,
                    "currency", Currency.code,
                    "won", func.bool_or(Ticket.won),
                    "demo", func.bool_and(Ticket.demo),
                    "image", func.concat(
                        f"{settings.back_url}/v1/file/games?path=",
                        func.coalesce(Jackpot.image, "default_jackpot.png")
                    ),
                    "status", Jackpot.status,
                    "total_amount", func.sum(Ticket.amount).label("total_amount"),
                    "ticket_count", func.count(Ticket.id).label("ticket_count"),
                    "prize", Jackpot.amount,
                    "endtime", func.date_part('epoch', Jackpot.scheduled_datetime),
                    "created", func.date_part('epoch', Jackpot.created_at),
                    "name", Jackpot.name,
                ))
            .select_from(Jackpot)
            .join(Currency, Currency.id == Jackpot.currency_id)
            .join(Ticket, Ticket.jackpot_id == Jackpot.id)
            .filter(Ticket.user_id == user.id)
            .group_by(
                Jackpot.id,
                Currency.code,
                Jackpot.name,
            )
            .order_by(Jackpot.scheduled_datetime.desc())
        )

    else:
        stmt = (
            select(
                func.json_build_object(
                    "id", Game.id,
                    "game_id", Game.id,
                    "currency", Currency.code,
                    "name", Game.name,
                    "image", func.concat(
                        f"{settings.back_url}/v1/file/games?path=",
                        func.coalesce(Game.image, "default_image.png")
                    ),
                    "status", Game.status,
                    "price", Game.price,
                    "won", func.bool_or(Ticket.won),
                    "demo", func.bool_and(Ticket.demo),
                    "max_limit_grid", Game.max_limit_grid,
                    "total_amount", func.sum(Ticket.amount).label("total_amount"),
                    "ticket_count", func.count(Ticket.id).label("ticket_count"),
                    "prize", Game.prize,
                    "endtime", func.date_part('epoch', Game.scheduled_datetime),
                    "created", func.date_part('epoch', Game.created_at),
                ))
            .select_from(Game)
            .join(Currency, Currency.id == Game.currency_id)
            .join(Ticket, Ticket.game_id == Game.id)
            .filter(Ticket.user_id == user.id)
            .group_by(
                Game.id,
                Game.name,
                Currency.code,
            )
            .order_by(Game.scheduled_datetime.desc())
        )

    count = stmt.order_by(None).with_only_columns(func.count())
    count = await db.execute(count)
    count = count.scalar() or 0

    items = await db.execute(stmt.offset(skip).limit(limit))
    items = items.scalars().fetchall()

    return MyGames(games=items, count=count)


@users_router.get(
    "/notifications",
    response_model=Notifications
)
async def get_notifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[Token, Depends(JWTBearer())],
    skip: int = 0,
    limit: int = 10,
):
    """
    Получение уведомлений для пользователя
    """
    stmt = (
        select(
            func.json_build_object(
                "id", Notification.id,
                "head", Notification.head,
                "body", Notification.body,
                "args_", Notification.args,
                "created", func.date_part('epoch', Notification.created_at)
            )
        )
        .select_from(Notification)
        .filter(Notification.user_id == token.id)
        .order_by(Notification.created_at.desc())
    )
    count_stmt = select(func.count(Notification.id)).filter(Notification.user_id == token.id)
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    notifications = await db.execute(stmt.offset(skip).limit(limit))
    notifications = notifications.scalars().all()

    await db.execute(
        update(Notification)
        .where(Notification.user_id == token.id)
        .values(read=True)
    )
    await db.commit()

    return {"items": notifications, "count": count}


@users_router.post(
    "/settings",
    tags=[Action.UPDATE],
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
    return "OK"

