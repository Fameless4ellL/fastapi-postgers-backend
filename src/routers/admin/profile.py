from typing import Annotated

from fastapi import status, Security, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import get_db
from src.models.user import Role, User, Document
from src.routers import admin
from src.schemes import BadResponse
from src.schemes.admin import (
    Profile,
)
from src.utils.dependencies import get_admin
from src.utils.validators import url_for


@admin.get(
    "/profile",
    responses={
        400: {"model": BadResponse},
        200: {"model": Profile}
    },
)
async def get_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Security(get_admin, scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value,
        'auth'
    ])],

):
    """
    Получение профиля пользователя
    """
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
        "twofa": bool(user.verified),
        "kyc": user.kyc,
        "avatar": url_for('static/avatars', filename=user.avatar_v1.name) if user.avatar_v1 else None,
        "document": documents,
    }

    return JSONResponse(
        content=Profile(**data).model_dump(),
        status_code=status.HTTP_200_OK
    )
