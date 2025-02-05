from fastapi import Depends, Path, status
from fastapi.responses import JSONResponse
from typing import Annotated, Optional

from sqlalchemy import func, select
from models.user import User, Role
from models.other import Ticket
from routers import admin
from routers.utils import get_admin, permission
from globals import scheduler
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import Admin, Admins, Users, UserInfo as UserScheme
from schemes.base import BadResponse


@admin.get("/healthcheck")
async def healthcheck(admin: Annotated[User, Depends(get_admin)]):
    """
    Test endpoint
    """
    return {"status": 200}


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
    offset: int = 0,
    limit: int = 10
):
    """
    Get all users
    """
    stmt = select(User).filter(User.role == "user").offset(offset).limit(limit)
    users = await db.execute(stmt)
    users = users.scalars().all()

    stmt = select(func.count(User.id)).filter(User.role == "user")
    count = await db.execute(stmt)
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
        "tickets": {"purchased": tickets or 0},
        "winnings": {"winnings": winnings or 0}
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=UserScheme(**data).model_dump()
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
    role: Optional[Role] = None
):
    """
    Get all admins
    """
    stmt = select(User).filter(
        User.role != "user"
    )
    if role:
        stmt = stmt.filter(User.role == role.value)

    admins = await db.execute(stmt)
    admins = admins.scalars().all()

    data = [
        {
            "id": admin.id,
            "username": admin.username,
            "phone_number": admin.phone_number,
            "country": admin.country
        }
        for admin in admins
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Admins(admins=data, count=len(data)).model_dump()
    )


@admin.get(
    "/admins/{admin_id}",
    responses={
        400: {"model": BadResponse},
        200: {"model": Admin},
    }
)
async def get_admin(
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
