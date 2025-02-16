import random
from fastapi import Depends, Path, Query, background, status, Security
from fastapi.responses import JSONResponse
from typing import Annotated, Optional
from pydantic_extra_types.country import CountryAlpha3

from sqlalchemy import func, select, or_
from models.user import User, Role
from models.other import Network, Currency
from routers import admin
from routers.admin import get_crud_router
from routers.utils import get_admin_token, send_mail
from globals import scheduler, aredis
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import (
    Admin,
    Admins,
    NetworkCreate,
    NetworkSchema,
    Networks,
    CurrencySchema,
    Currencies,
    CurrencyCreate,
    CurrencyUpdate,
    NetworkUpdate
)
from schemes.base import BadResponse


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


get_crud_router(
    model=Network,
    prefix="/networks",
    schema=Networks,
    get_schema=NetworkSchema,
    create_schema=NetworkCreate,
    update_schema=NetworkUpdate
)
get_crud_router(
    model=Currency,
    prefix="/currencies",
    schema=Currencies,
    get_schema=CurrencySchema,
    create_schema=CurrencyCreate,
    update_schema=CurrencyUpdate
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
