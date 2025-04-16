import os
import random
from fastapi import Depends, Path, Query, background, status, Security, UploadFile
from fastapi.responses import JSONResponse
from typing import Annotated, Union
from models.log import Action
from pydantic_extra_types.country import CountryAlpha3

from sqlalchemy import func, select, or_
from models.user import User, Role
from models.other import Network, Currency
from routers import admin
from routers.admin import get_crud_router
from routers.utils import Token, get_admin_token, send_mail, url_for
from globals import scheduler, aredis
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import get_db
from schemes.admin import (
    Admin,
    AdminCreate,
    Admins,
    AdminFilter,
    NetworkCreate,
    NetworkSchema,
    Networks,
    CurrencySchema,
    Currencies,
    CurrencyCreate,
    CurrencyUpdate,
    NetworkUpdate,
    Empty,
    Profile
)
from schemes.base import BadResponse, JsonForm


@admin.get(
    "/jobs",
    dependencies=[Security(get_admin_token, scopes=[Role.SUPER_ADMIN.value])]
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
    update_schema=NetworkUpdate,
    filters=Annotated[Empty, Depends(Empty)],
    security_scopes=[Role.SUPER_ADMIN.value]
)
get_crud_router(
    model=Currency,
    prefix="/currencies",
    schema=Currencies,
    get_schema=CurrencySchema,
    create_schema=CurrencyCreate,
    update_schema=CurrencyUpdate,
    filters=Annotated[Empty, Depends(Empty)],
    security_scopes=[Role.SUPER_ADMIN.value]
)


@admin.get(
    "/admins",
    responses={
        400: {"model": BadResponse},
        200: {"model": Admins},
    },
)
async def get_admin_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Annotated[AdminFilter, Depends(AdminFilter)],
    token: Annotated[Token, Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
        ]
    )],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get all admins
    """
    stmt = select(User).filter(User.role != "user")
    if item.role:
        roles = [role.label for role in item.role]
        stmt = stmt.filter(User.role.in_(roles))

    if item.countries:
        stmt = stmt.filter(User.country.in_(item.countries))

    if item.filter:
        stmt = stmt.filter(
            or_(
                User.username.ilike(f"%{item.filter}%"),
                User.phone_number.ilike(f"%{item.filter}%"),
            )
        )

    admins = await db.execute(stmt.offset(offset).limit(limit))
    admins = admins.scalars().all()

    count = await db.execute(stmt.with_only_columns(func.count(User.id)))
    count = count.scalar()

    scope = next(iter(token.scopes), None)

    data = [
        {
            "id": admin.id,
            "username": f"{admin.firstname} {admin.lastname}",
            "phone_number": admin.phone_number if scope == Role.GLOBAL_ADMIN.value else None,
            "email": admin.email if scope == Role.GLOBAL_ADMIN.value else None,
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
    dependencies=[Security(get_admin_token, scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
    ])],
    responses={
        400: {"model": BadResponse},
        200: {"model": Profile},
    },
)
async def get_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin_id: Annotated[int, Path()],
):
    """
    Get all admins
    """
    stmt = select(User).filter(User.id == admin_id, User.role != "user")
    user = await db.execute(stmt)
    user = user.scalar()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Admin not found"},
        )

    data = {
        "id": user.id,
        "telegram": user.telegram,
        "fullname": f"{user.firstname} {user.lastname}",
        "language_code": user.language_code,
        "phone_number": user.phone_number,
        "country": user.country,
        "email": user.email,
        "role": user.role,
        "active": user.active,
        "kyc": user.kyc,
        "avatar": url_for('static/avatars', filename=user.avatar) if user.avatar else None,
        "document": url_for('static/kyc', filename=user.document) if user.document else None,
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK, content=Profile(**data).model_dump()
    )


@admin.post(
    "/admins/create",
    tags=[Action.ADMIN_CREATE],
    responses={
        400: {"model": BadResponse},
        201: {"model": Admin},
    },
)
async def create_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[Token, Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
        ]
    )],
    item: Annotated[AdminCreate, JsonForm],
    bg: background.BackgroundTasks,
    avatar: UploadFile,
    document: list[UploadFile],
):
    """
    Create new admin
    """
    scope = next(iter(token.scopes), None)
    if (
        scope == Role.GLOBAL_ADMIN.value
        and item.role in {Role.SUPER_ADMIN.value, Role.ADMIN.value}
    ):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "You can't create this admin"},
        )

    stmt = select(User)

    if item.phone_number:
        stmt = stmt.filter(User.phone_number == item.phone_number)

    if item.username:
        stmt = stmt.filter(User.username != item.username)

    exists = await db.execute(stmt)
    exists = exists.scalars().all()

    if exists:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Unique field error"}
        )

    new_admin = User(**item.model_dump(exclude={"id"}))
    db.add(new_admin)
    await db.commit()
    await db.refresh(new_admin)

    if not avatar.content_type.startswith("image"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Invalid file type"
        )

    if not document.content_type.startswith("image"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content="Invalid file type"
        )

    if avatar:
        avatar = await save_file(new_admin, avatar, "static/avatars", "avatar")
    if document:
        document = await save_file(new_admin, document, "static/kyc", "document")

    new_admin.avatar = avatar
    new_admin.document = document

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
        status_code=status.HTTP_201_CREATED, content="OK", background=bg
    )


@admin.put(
    "/admins/{admin_id}/update",
    tags=[Action.ADMIN_UPDATE],
    dependencies=[Security(get_admin_token, scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
    ])],
    responses={
        400: {"model": BadResponse},
        201: {"model": Admin},
    },
)
async def update_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Annotated[AdminCreate, JsonForm()],
    admin_id: Annotated[int, Path()],
    avatar: Union[UploadFile, None] = None,
    document: Union[UploadFile, None] = None
):
    """
    Update admin
    """
    admin = await db.execute(select(User).filter(User.id == admin_id))
    admin = admin.scalar()

    if not admin:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Admin not found"},
        )

    stmt = select(User)

    if item.phone_number:
        stmt = stmt.filter(User.phone_number == item.phone_number)
    if item.telegram_id:
        stmt = stmt.filter(User.telegram_id != item.telegram_id)
    if item.username:
        stmt = stmt.filter(User.username != item.username)

    exists = await db.execute(stmt)
    exists = exists.scalars().all()

    if exists:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Unique field error"}
        )

    for key, value in item.model_dump().items():
        setattr(admin, key, value)

    if avatar:
        if not avatar.content_type.startswith("image"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content="Invalid file type"
            )
        if admin.avatar:
            try:
                os.remove(f"static/avatars/{admin.avatar}")
            except FileNotFoundError:
                pass

        avatar = await save_file(admin, avatar, "static/avatars", "avatar")
    if document:
        if not document.content_type.startswith("image"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content="Invalid file type"
            )
        if admin.document:
            try:
                os.remove(f"static/kyc/{admin.document}")
            except FileNotFoundError:
                pass

        document = await save_file(admin, document, "static/kyc", "document")

    admin.avatar = avatar
    admin.document = document

    db.add(admin)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content="OK"
    )


async def save_file(model: object, file: UploadFile, directory: str, field: str):
    os.makedirs(directory, exist_ok=True)

    # Save file to disk
    filename, file_extension = os.path.splitext(file.filename)
    filename = filename.replace(" ", "_")
    setattr(model, field, f"{filename}_{model.id}{file_extension}")

    file_path = os.path.join(
        directory,
        f"{filename}_{model.id}{file_extension}"
    )
    with open(file_path, "wb") as f:
        f.write(await file.read())
    return f"{filename}_{model.id}{file_extension}"


@admin.delete(
    "/admins/{admin_id}",
    tags=[Action.ADMIN_DELETE],
    responses={
        400: {"model": BadResponse},
        200: {"model": Admin},
    },
)
async def delete_admin(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[Token, Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
        ]
    )],
    admin_id: Annotated[int, Path()],
):
    """
    Delete admin
    """
    if token.id == admin_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "You can't delete yourself"},
        )

    admin = await db.execute(select(User).filter(User.id == admin_id))
    admin = admin.scalar()

    if not admin:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Admin not found"},
        )

    scope = next(iter(token.scopes), None)
    if scope == Role.ADMIN.value and admin.role in {Role.SUPER_ADMIN.value, Role.ADMIN.value}:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "You can't delete this admin"},
        )

    admin.active = not admin.active
    db.add(admin)
    await db.commit()
    await aredis.delete(f"TOKEN:ADMINS:{admin.id}")

    return JSONResponse(
        status_code=status.HTTP_200_OK, content="OK"
    )
