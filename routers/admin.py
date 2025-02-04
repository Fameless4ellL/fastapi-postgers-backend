from fastapi import Depends, Path, status
from fastapi.responses import JSONResponse
from typing import Annotated

from sqlalchemy import func, select
from models.user import User
from models.other import Ticket
from routers import admin
from routers.utils import get_admin
from globals import scheduler
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import Users, UserInfo as UserScheme
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
    stmt = select(User).offset(offset).limit(limit)
    users = await db.execute(stmt)
    users = users.scalars().all()

    stmt = select(func.count(User.id))
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
    stmt = select(User).filter(User.id == user_id)
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
