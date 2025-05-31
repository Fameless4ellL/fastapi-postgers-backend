import random
from typing import Annotated, Union

from fastapi import Depends, Path, background, status, Security, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, or_, delete, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.globals import aredis
from src.models.db import get_db
from src.models.log import Action
from src.models.other import Network, Currency
from src.models.user import User, Role, Document
from src.routers import admin
from src.routers.admin import get_crud_router
from src.utils.dependencies import Token, get_admin_token, send_mail, is_field_unique
from src.utils.validators import url_for
from src.schemes.admin import (
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
    Profile,
    AdminRoles
)
from src.schemes import BadResponse, JsonForm
from settings import settings

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

    if item.status:
        statuss = [_status.label for _status in item.status]
        stmt = stmt.filter(User.active.in_(statuss))

    if item.countries:
        stmt = stmt.filter(User.country.in_(item.countries))

    if item.filter:
        stmt = stmt.filter(
            or_(
                func.cast(User.id, String).ilike(f"%{item.filter}%"),
                User.firstname.ilike(f"%{item.filter}%"),
                User.lastname.ilike(f"%{item.filter}%"),
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
            "id": a.id,
            "username": a.username,
            "fullname": f"{a.firstname} {a.lastname}",
            "active": a.active,
            "telegram": a.telegram,
            "phone_number": a.phone_number if scope != Role.GLOBAL_ADMIN.value else None,
            "email": a.email if scope != Role.GLOBAL_ADMIN.value else None,
            "role": a.role,
            "country": a.country,
        }
        for a in admins
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Admins(admins=data, count=count).model_dump(mode="json"),
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

    docs = await db.execute(
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
        .limit(5)
    )
    documents = docs.scalars().all()
    documents = [
        url_for("static/kyc", path=doc.file.name)
        for doc in documents
    ]

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
        "avatar": url_for('static/avatars', filename=user.avatar_v1.name) if user.avatar_v1 else None,
        "document": documents
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
    item: Annotated[AdminCreate, JsonForm()],
    bg: background.BackgroundTasks,
    avatar: UploadFile,
    documents: list[UploadFile],
):
    """
    Create new admin
    """

    scope = next(iter(token.scopes), None)
    if (
            scope == Role.GLOBAL_ADMIN.value
            and item.role in {AdminRoles.SUPER_ADMIN, AdminRoles.ADMIN}
    ):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "You can't create this admin"},
        )

    errors = [
        (name, await is_field_unique(db, User, field_name=name, field_value=value))
        for name, value in [
            ("email", item.email),
            ("phone_number", item.phone_number),
            ("telegram", item.telegram)
        ]
    ]
    if not all(error for _, error in errors):
        raise RequestValidationError(
            errors=[
                {
                    "loc": ["body", field],
                    "msg": f"{field} is already taken",
                    "type": "value_error"
                }
                for field, error in errors
                if error is False
            ]
        )

    new_admin = User(**item.model_dump(exclude={"id"}))
    db.add(new_admin)
    await db.commit()
    await db.refresh(new_admin)

    if avatar:
        new_admin.avatar_v1 = avatar

    for file in documents:
        if not file.content_type.startswith("image"):
            raise RequestValidationError(
                errors=[
                    {
                        "loc": ["body", "documents"],
                        "msg": "Invalid file type",
                        "type": "value_error"
                    }
                ]
            )

        file.filename = f"{new_admin.id}_{file.filename}"
        doc = Document(
            user_id=new_admin.id,
            file=file
        )
        db.add(doc)

    db.add(new_admin)
    await db.commit()

    code = random.randint(100000, 999999)
    await aredis.set(f"EMAIL:{new_admin.email}", code, ex=60 * 15)

    bg.add_task(
        send_mail,
        "New Admin",
        (
            f"New admin {new_admin.username} has been created. your code is {code}",
            f" {settings.web_app_url}/registration/{code}"
        ),
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
    documents: Union[list[UploadFile], None] = None
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

    errors = [
        (name, await is_field_unique(db, User, field_name=name, field_value=value, exclude_id=admin.id))
        for name, value in [
            ("email", item.email),
            ("phone_number", item.phone_number),
            ("telegram", item.telegram)
        ]
    ]

    if not all(error for _, error in errors):
        raise RequestValidationError(
            errors=[
                {
                    "loc": ["body", field],
                    "msg": f"{field} is already taken",
                    "type": "value_error"
                }
                for field, error in errors
                if error is False
            ]
        )

    for key, value in item.model_dump().items():
        setattr(admin, key, value)

    if avatar:
        admin.avatar_v1 = avatar
    if documents:
        stmt = delete(Document).filter_by(user_id=admin.id)
        await db.execute(stmt)

        for file in documents:
            if not file.content_type.startswith("image"):
                raise RequestValidationError(
                    errors=[
                        {
                            "loc": ["body", "documents"],
                            "msg": "Invalid file type",
                            "type": "value_error"
                        }
                    ]
                )

            file.filename = f"{admin.id}_{file.filename}"
            doc = Document(
                user_id=admin.id,
                file=file
            )
            db.add(doc)

    db.add(admin)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content="OK"
    )


@admin.delete(
    "/admins/{admin_id}",
    tags=[Action.ADMIN_DELETE],
    responses={
        400: {"model": BadResponse},
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
