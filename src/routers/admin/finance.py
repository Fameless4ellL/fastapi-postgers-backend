from typing import Annotated

from fastapi import Depends, Path, status, Security
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession


from src.models.db import get_db
from src.models.user import User, Role, Document, BalanceChangeHistory
from src.routers import admin
from src.utils.dependencies import Token, get_admin_token
from src.utils.validators import url_for
from src.schemes.admin import (
    Admins,
    Profile,
    Operations,
    OperationFilter
)
from src.schemes import BadResponse


@admin.get(
    "/operations",
    responses={
        400: {"model": BadResponse},
        200: {"model": Operations},
    },
)
async def get_operation_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Annotated[OperationFilter, Depends(OperationFilter)],
    token: Annotated[Token, Security(
        get_admin_token,
        scopes=[
            Role.GLOBAL_ADMIN.value,
            Role.ADMIN.value,
            Role.SUPER_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.FINANCIER.value,
            Role.SUPPORT.value
        ]
    )],
    offset: int = 0,
    limit: int = 10,
):
    """
    Get operations list
    """
    stmt = select(User).filter(User.role != "user")
    if item.role:
        roles = [role.label for role in item.role]
        stmt = stmt.filter(BalanceChangeHistory.role.in_(roles))

    if item.status:
        statuss = [_status.label for _status in item.status]
        stmt = stmt.filter(User.active.in_(statuss))

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

    docs = await db.execute(
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
        .limit(4)
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
