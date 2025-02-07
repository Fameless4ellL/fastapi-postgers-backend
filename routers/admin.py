from fastapi import Depends, Path, Query, Request, status
from fastapi.responses import JSONResponse
from typing import Annotated, Optional
from pydantic_extra_types.country import CountryAlpha3

from sqlalchemy import func, select, or_
from models.user import Balance, User, Role
from models.other import Game, Ticket, GameInstance
from routers import admin
from routers.utils import get_admin, permission
from globals import scheduler
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import Admin, Admins, Users, UserInfo as UserScheme, UserGames
from schemes.auth import AccessToken, AdminLogin
from schemes.base import BadResponse
from globals import aredis
from utils.signature import create_access_token, verify_password


@admin.get("/jobs")
async def get_jobs(admin: Annotated[User, Depends(get_admin)]):
    """
    Get active scheduler jobs after game creation(GameInstance)
    """
    jobs = scheduler.get_jobs()
    data = [
        {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S"),
            "args": job.args
        }
        for job in jobs
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=data
    )


@admin.post(
    "/login",
    responses={
        400: {"model": BadResponse},
        200: {"model": AccessToken},
    }
)
async def login(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminLogin,
):
    userdb = await db.execute(
        select(User).filter(User.username == user.username)
    )
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

    access_token = create_access_token(
        data={"username": userdb.username, "password": userdb.password}
    )

    return JSONResponse(
        status_code=200, content={"access_token": access_token, "token_type": "bearer"}
    )


@admin.get(
    "/users",
    responses={
        400: {"model": BadResponse},
        200: {"model": Users},
    }
)
async def get_users(
    admin: Annotated[User, Depends(get_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    query: Annotated[Optional[str], Query(...)] = None,
    country: Annotated[Optional[CountryAlpha3], Query(...)] = None,
    offset: int = 0,
    limit: int = 10
):
    """
    Get all users
    """
    stmt = select(User).filter(User.role == "user")
    if country:
        stmt = stmt.filter(User.country == country)

    if query:
        stmt = stmt.filter(or_(
            User.username.ilike(f"%{query}%"),
            User.phone_number.ilike(f"%{query}%"),
        ))

    users = await db.execute(stmt.offset(offset).limit(limit))
    users = users.scalars().all()

    count = await db.execute(stmt.with_only_columns(func.count(User.id)))
    count = count.scalar()

    data = [
        {
            "id": user.id,
            "username": user.username,
            "phone_number": user.phone_number,
            "country": user.country
        }
        for user in users
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Users(users=data, count=count).model_dump()
    )


@admin.get(
    "/users/{user_id}",
    responses={
        400: {"model": BadResponse},
        200: {"model": UserScheme},
    }
)
async def get_user(
    admin: Annotated[User, Depends(get_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
):
    """
    Get all users
    """
    stmt = select(User).filter(
        User.id == user_id,
        User.role == "user"
    )
    user = await db.execute(stmt)
    user = user.scalars().first()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User not found"}
        )

    tickets = await db.execute(
        select(func.count(Ticket.id))
        .filter(User.id == user_id)
    )
    tickets = tickets.scalar()
    winnings = await db.execute(
        select(func.sum(Ticket.amount))
        .filter(
            Ticket.id == user_id,
            Ticket.won.is_(True)
        )
    )
    winnings = winnings.scalar()
    balance_result = await db.execute(
        select(Balance)
        .filter(Balance.user_id == user.id)
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
        "winnings": {"winnings": winnings or 0}
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=UserScheme(**data).model_dump()
    )


@admin.get(
    "/users/{user_id}/games",
    responses={
        400: {"model": BadResponse},
        200: {"model": UserGames},
    }
)
async def get_user_games(
    admin: Annotated[User, Depends(get_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Path()],
    offset: int = 0,
    limit: int = 10
):
    """
    Get all users
    """
    stmt = select(User).filter(
        User.id == user_id,
        User.role == "user"
    )
    user = await db.execute(stmt)
    user = user.scalars().first()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User not found"}
        )

    stmt = (
        select(
            GameInstance.id,
            Game.name,
            GameInstance.scheduled_datetime,
            func.count(Ticket.id).label("tickets_purchased"),
            func.sum(func.coalesce(Ticket.amount, 0)).filter(Ticket.won.is_(True)).label("won_amount")
        )
        .join(Ticket, Ticket.game_instance_id == GameInstance.id)
        .join(Game, Game.id == GameInstance.game_id)
        .filter(Ticket.user_id == user_id)
        .group_by(GameInstance.id, Game.name)
    )

    result = await db.execute(stmt.offset(offset).limit(limit))
    game_instances = result.fetchall()

    count = await db.execute(stmt.with_only_columns(func.count(GameInstance.id)))
    count = count.scalar()

    data = [
        {
            "game_instance_id": game_instance.id,
            "game_name": game_instance.name,
            "scheduled_datetime": game_instance.scheduled_datetime.strftime("%Y-%m-%d %H:%M:%S") if game_instance.scheduled_datetime else None,
            "tickets_purchased": game_instance.tickets_purchased,
            "amount": float(game_instance.won_amount),
        }
        for game_instance in game_instances
    ]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=UserGames(games=data, count=len(data)).model_dump()
    )


@admin.get(
    "/admins",
    responses={
        400: {"model": BadResponse},
        200: {"model": Admins},
    }
)
async def get_admins(
    admin: Annotated[User, Depends(permission([Role.GLOBAL_ADMIN.value]))],
    db: Annotated[AsyncSession, Depends(get_db)],
    query: Annotated[Optional[str], Query(...)] = None,
    country: Annotated[Optional[CountryAlpha3], Query(...)] = None,
    role: Optional[Role] = None,
    offset: int = 0,
    limit: int = 10
):
    """
    Get all admins
    """
    stmt = select(User).filter(
        User.role != "user"
    )
    if role:
        stmt = stmt.filter(User.role == role.value)

    if country:
        stmt = stmt.filter(User.country == country)

    if query:
        stmt = stmt.filter(or_(
            User.username.ilike(f"%{query}%"),
            User.phone_number.ilike(f"%{query}%"),
        ))

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
            "country": admin.country
        }
        for admin in admins
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Admins(admins=data, count=count).model_dump()
    )


@admin.get(
    "/admins/{admin_id}",
    responses={
        400: {"model": BadResponse},
        200: {"model": Admin},
    }
)
async def get_admin_(
    admin: Annotated[User, Depends(permission([Role.GLOBAL_ADMIN.value]))],
    db: Annotated[AsyncSession, Depends(get_db)],
    admin_id: Annotated[int, Path()],
):
    """
    Get all admins
    """
    stmt = select(User).filter(
        User.id == admin_id,
        User.role != "user"
    )
    admin = await db.execute(stmt)
    admin = admin.scalars().first()

    if not admin:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Admin not found"}
        )

    data = {
        "id": admin.id,
        "username": f"{admin.firtname} {admin.lastname}",
        "phone_number": admin.phone_number,
        "country": admin.country,
        "email": admin.email,
        "role": admin.role,
        "created_at": admin.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": admin.updated_at.strftime("%Y-%m-%d %H:%M:%S")
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Admin(**data).model_dump()
    )


@admin.post(
    "/admins/create",
    responses={
        400: {"model": BadResponse},
        201: {"model": Admin},
    }
)
async def create_admin(
    admin: Annotated[User, Depends(permission([Role.GLOBAL_ADMIN.value]))],
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Admin,
):
    """
    Create new admin
    """
    new_admin = User(**item.model_dump(exclude={"id"}))
    db.add(new_admin)
    await db.commit()
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content="created"
    )
