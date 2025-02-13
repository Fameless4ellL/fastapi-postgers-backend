import random
from fastapi import Depends, Path, Query, background, status, Security
from fastapi.responses import JSONResponse
from typing import Annotated, Optional
from pydantic_extra_types.country import CountryAlpha3

from sqlalchemy import func, select, or_
from models.user import Balance, User, Role
from models.other import Game, Network, Ticket, GameInstance, JackpotInstance, Jackpot, Currency
from routers import admin
from routers.utils import get_admin_token, send_mail
from globals import scheduler, aredis
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import (
    Admin,
    Admins,
    ResetPassword,
    UserJackpots,
    UserTickets,
    Users,
    UserInfo as UserScheme,
    UserGames,
    AdminLogin,
    NetworkSchema,
    CurrencySchema
)
from schemes.auth import AccessToken
from schemes.base import BadResponse
from utils.signature import (
    create_access_token,
    get_password_hash,
    verify_password,
    ACCESS_TOKEN_EXPIRE_MINUTES
)


@admin.get(
    "/jobs",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])]
)
async def get_jobs():
    """
    Get active scheduler jobs after game creation(GameInstance)
    """
    jobs = scheduler.get_jobs()
    data = [
        {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S"),
            "args": job.args,
        }
        for job in jobs
    ]
    return JSONResponse(status_code=status.HTTP_200_OK, content=data)


@admin.get(
    "/networks",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_networks(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get all networks
    """
    stmt = select(Network)
    networks = await db.execute(stmt)
    networks = networks.scalars().all()

    data = [
        {
            "id": network.id,
            "name": network.name,
            "url": network.rpc_url,
            "chain_id": network.chain_id,
        }
        for network in networks
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data,
    )


@admin.post(
    "/networks/create",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
    },
)
async def create_network(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: NetworkSchema,
):
    """
    Create new network
    """
    new_network = Network(**item.model_dump())
    db.add(new_network)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content="created"
    )


@admin.get(
    "/currencies",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
    },
)
async def get_currencies(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Get all currencies
    """
    stmt = select(Currency)
    currencies = await db.execute(stmt)
    currencies = currencies.scalars().all()

    data = [
        {
            "id": currency.id,
            "name": currency.name,
            "code": currency.code,
            "network": currency.network_id,
        }
        for currency in currencies
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data,
    )


@admin.post(
    "/currencies/create",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
    },
)
async def create_currency(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: CurrencySchema,
):
    """
    Create new currency
    """
    new_network = Currency(**item.model_dump())
    db.add(new_network)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content="created"
    )


@admin.post(
    "/login",
    responses={
        400: {"model": BadResponse},
        200: {"model": AccessToken},
    },
)
async def login(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminLogin,
):
    """
    Admin login
    """
    stmt = select(User).filter(
        or_(
            User.email == user.login,
            User.username == user.login
        ),
        User.role != "user"
    )
    userdb = await db.execute(stmt)
    userdb = userdb.scalar()
    if not userdb:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"message": "User not found"}
        )

    if not user or not verify_password(
        user.password.get_secret_value(), userdb.password
    ):
        return JSONResponse(
            status_code=400, content={"message": "Invalid phone number or password"}
        )

    data = {
        "id": userdb.id,
        "scopes": [userdb.role],
    }

    access_token = create_access_token(data=data)

    await aredis.set(
        f"TOKEN:ADMINS:{userdb.id}",
        access_token,
        ex=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    return JSONResponse(
        status_code=200, content={"access_token": access_token, "token_type": "bearer"}
    )


@admin.get(
    "/users",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": Users},
    },
)
async def get_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    query: Annotated[Optional[str], Query(...)] = None,
    country: Annotated[Optional[CountryAlpha3], Query(...)] = None,
    offset: int = 0,
    limit: int = 10,
):
    """
    Get all users
    """
    stmt = select(User).filter(User.role == "user")
    if country:
        stmt = stmt.filter(User.country == country)

    if query:
        stmt = stmt.filter(
            or_(
                User.username.ilike(f"%{query}%"),
                User.phone_number.ilike(f"%{query}%"),
            )
        )

    users = await db.execute(stmt.offset(offset).limit(limit))
    users = users.scalars().all()

    count = await db.execute(stmt.with_only_columns(func.count(User.id)))
    count = count.scalar()

    data = [
        {
            "id": user.id,
            "username": user.username,
            "phone_number": user.phone_number,
            "country": user.country,
        }
        for user in users
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Users(users=data, count=count).model_dump(),
    )


@admin.get(
    "/users/{user_id}",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": UserScheme},
    },
)
async def get_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
):
    """
    Get all users
    """
    stmt = select(User).filter(User.id == user_id, User.role == "user")
    user = await db.execute(stmt)
    user = user.scalars().first()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User not found"},
        )

    tickets = await db.execute(select(func.count(Ticket.id)).filter(User.id == user_id))
    tickets = tickets.scalar()
    winnings = await db.execute(
        select(func.sum(Ticket.amount)).filter(
            Ticket.id == user_id, Ticket.won.is_(True)
        )
    )
    winnings = winnings.scalar()
    balance_result = await db.execute(
        select(Balance).filter(Balance.user_id == user.id)
    )
    balance = balance_result.scalar()

    if not balance:
        balance = Balance(user_id=user.id)
        db.add(balance)
        await db.commit()

    total_balance = balance.balance

    data = {
        "id": user.id,
        "username": user.username,
        "telegram_id": user.telegram_id,
        "language_code": user.language_code,
        "phone_number": user.phone_number,
        "country": user.country,
        "email": user.email,
        "role": user.role,
        "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "balance": total_balance,
        "tickets": {"purchased": tickets or 0},
        "winnings": {"winnings": winnings or 0},
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK, content=UserScheme(**data).model_dump()
    )


@admin.get(
    "/users/{user_id}/games",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": UserGames},
    },
)
async def get_user_games(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get all user's games
    """
    stmt = select(User).filter(User.id == user_id, User.role == "user")
    user = await db.execute(stmt)
    user = user.scalars().first()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User not found"},
        )

    stmt = (
        select(
            GameInstance.id,
            Game.name,
            GameInstance.scheduled_datetime,
            func.count(Ticket.id).label("tickets_purchased"),
            func.sum(func.coalesce(Ticket.amount, 0))
            .filter(Ticket.won.is_(True))
            .label("won_amount"),
        )
        .join(Ticket, Ticket.game_instance_id == GameInstance.id)
        .join(Game, Game.id == GameInstance.game_id)
        .filter(Ticket.user_id == user_id)
        .group_by(GameInstance.id, Game.name)
    )

    result = await db.execute(stmt.offset(offset).limit(limit))
    game_instances = result.fetchall()

    count = await db.execute(stmt.with_only_columns(func.count(GameInstance.id)))
    count = count.scalar() or 0

    data = [
        {
            "game_instance_id": game_instance.id,
            "game_name": game_instance.name,
            "scheduled_datetime": (
                game_instance.scheduled_datetime.strftime("%Y-%m-%d %H:%M:%S")
                if game_instance.scheduled_datetime
                else None
            ),
            "tickets_purchased": game_instance.tickets_purchased,
            "amount": float(game_instance.won_amount),
        }
        for game_instance in game_instances
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=UserGames(games=data, count=count).model_dump(),
    )


@admin.get(
    "/users/{user_id}/games/{game_id}",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": UserTickets},
    },
)
async def get_user_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
    game_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get user's tickets for a specific game
    """
    stmt = (
        select(
            Ticket.id,
            Game.name.label("game_name"),
            Ticket.numbers,
            Ticket.created_at.label("date_and_time"),
            Ticket.won,
            Ticket.amount
        )
        .join(GameInstance, GameInstance.id == Ticket.game_instance_id)
        .join(Game, Game.id == GameInstance.game_id)
        .filter(
            Ticket.user_id == user_id,
            Game.id == game_id,
        )
    )

    result = await db.execute(stmt.offset(offset).limit(limit))
    tickets = result.fetchall()

    count = await db.execute(stmt.with_only_columns(func.count(Ticket.id)))
    count = count.scalar() or 0

    data = [
        {
            "id": ticket.id,
            "game_name": ticket.game_name,
            "numbers": ticket.numbers,
            "date_and_time": (
                ticket.date_and_time.strftime("%Y-%m-%d %H:%M:%S")
                if ticket.date_and_time
                else None
            ),
            "won": ticket.won,
            "amount": float(ticket.amount),
        }
        for ticket in tickets
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"tickets": data, "count": len(data)},
    )


@admin.get(
    "/users/{user_id}/jackpots",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": UserJackpots},
    },
)
async def get_user_jackpots(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get user's jackpots for a specific game
    """
    stmt = (
        select(
            JackpotInstance.id,
            Jackpot.name,
            JackpotInstance.scheduled_datetime,
            func.count(Ticket.id).label("tickets_purchased"),
        )
        .join(Ticket, Ticket.jackpot_id == JackpotInstance.id)
        .join(Jackpot, Jackpot.id == JackpotInstance.jackpot_id)
        .filter(Ticket.user_id == user_id)
        .group_by(JackpotInstance.id, Jackpot.name)
    )

    result = await db.execute(stmt.offset(offset).limit(limit))
    game_instances = result.fetchall()

    count = await db.execute(stmt.with_only_columns(func.count(JackpotInstance.id)))
    count = count.scalar() or 0

    data = [
        {
            "game_instance_id": game_instance.id,
            "game_name": game_instance.name,
            "scheduled_datetime": (
                game_instance.scheduled_datetime.strftime("%Y-%m-%d %H:%M:%S")
                if game_instance.scheduled_datetime
                else None
            ),
            "tickets_purchased": game_instance.tickets_purchased,
        }
        for game_instance in game_instances
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=UserJackpots(games=data, count=count).model_dump(),
    )


@admin.get(
    "/users/{user_id}/jackpots/{game_id}",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": UserTickets},
    },
)
async def get_user_tickets_by_jackpots(
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
    game_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get user's tickets for a specific jackpot
    """
    stmt = (
        select(
            Ticket.id,
            Jackpot.name.label("game_name"),
            Ticket.numbers,
            Ticket.created_at.label("date_and_time"),
            Ticket.won,
            Ticket.amount
        )
        .join(JackpotInstance, JackpotInstance.id == Ticket.jackpot_id)
        .join(Jackpot, Jackpot.id == JackpotInstance.jackpot_id)
        .filter(
            Ticket.user_id == user_id,
            Jackpot.id == game_id,
        )
    )

    result = await db.execute(stmt.offset(offset).limit(limit))
    tickets = result.fetchall()

    count = await db.execute(stmt.with_only_columns(func.count(Ticket.id)))
    count = count.scalar() or 0

    data = [
        {
            "id": ticket.id,
            "game_name": ticket.game_name,
            "numbers": ticket.numbers,
            "date_and_time": (
                ticket.date_and_time.strftime("%Y-%m-%d %H:%M:%S")
                if ticket.date_and_time
                else None
            ),
            "won": ticket.won,
            "amount": float(ticket.amount),
        }
        for ticket in tickets
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"tickets": data, "count": len(data)},
    )


@admin.get(
    "/admins",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": Admins},
    },
)
async def get_admins(
    db: Annotated[AsyncSession, Depends(get_db)],
    query: Annotated[Optional[str], Query(...)] = None,
    country: Annotated[Optional[CountryAlpha3], Query(...)] = None,
    role: Optional[Role] = None,
    offset: int = 0,
    limit: int = 10,
):
    """
    Get all admins
    """
    stmt = select(User).filter(User.role != "user")
    if role:
        stmt = stmt.filter(User.role == role.value)

    if country:
        stmt = stmt.filter(User.country == country)

    if query:
        stmt = stmt.filter(
            or_(
                User.username.ilike(f"%{query}%"),
                User.phone_number.ilike(f"%{query}%"),
            )
        )

    admins = await db.execute(stmt.offset(offset).limit(limit))
    admins = admins.scalars().all()

    count = await db.execute(stmt.with_only_columns(func.count(User.id)))
    count = count.scalar()

    data = [
        {
            "id": admin.id,
            "username": admin.username,
            "phone_number": admin.phone_number,
            "email": admin.email,
            "role": admin.role,
            "country": admin.country,
        }
        for admin in admins
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Admins(admins=data, count=count).model_dump(),
    )


@admin.get(
    "/admins/{admin_id}",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
        200: {"model": Admin},
    },
)
async def get_admin_(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin_id: Annotated[int, Path()],
):
    """
    Get all admins
    """
    stmt = select(User).filter(User.id == admin_id, User.role != "user")
    admin = await db.execute(stmt)
    admin = admin.scalars().first()

    if not admin:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Admin not found"},
        )

    data = {
        "id": admin.id,
        "username": f"{admin.firtname} {admin.lastname}",
        "phone_number": admin.phone_number,
        "country": admin.country,
        "email": admin.email,
        "role": admin.role,
        "created_at": admin.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": admin.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK, content=Admin(**data).model_dump()
    )


@admin.post(
    "/admins/create",
    dependencies=[Security(get_admin_token, scopes=[Role.GLOBAL_ADMIN.value])],
    responses={
        400: {"model": BadResponse},
        201: {"model": Admin},
    },
)
async def create_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Admin,
    bg: background.BackgroundTasks,
):
    """
    Create new admin
    """
    new_admin = User(**item.model_dump(exclude={"id"}))
    db.add(new_admin)
    await db.commit()

    code = random.randint(100000, 999999)
    await aredis.set(f"EMAIL:{new_admin.email}", code, ex=60*15)

    bg.add_task(
        send_mail,
        "New Admin",
        f"New admin {new_admin.username} has been created",
        new_admin.email,
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content="created", background=bg
    )


@admin.post(
    "/reset",
    responses={
        400: {"model": BadResponse},
    },
)
async def reset_password(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: ResetPassword,
    bg: background.BackgroundTasks,
):
    """
    Reset password
    """
    stmt = select(User).filter(
        User.email == item.email,
        User.role != "user",
    )
    user = await db.execute(stmt)
    user = user.scalar()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User not found"},
        )

    if not await aredis.exists(f"EMAIL:{user.email}"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Code expired"},
        )

    code = await aredis.get(f"EMAIL:{user.email}").decode('utf-8')
    if code != item.code:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Invalid code"},
        )

    hashed_password = get_password_hash(item.password.get_secret_value())
    user.password = hashed_password
    await db.commit()

    bg.add_task(
        send_mail,
        "Password Reset",
        "Your password has been reset",
        user.email,
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content="OK")
