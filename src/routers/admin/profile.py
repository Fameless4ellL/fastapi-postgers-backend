from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import get_db
from src.models.user import User, Document
from src.routers import admin
from src.schemes.admin import (
    Profile,
)
from src.utils.dependencies import get_admin


@admin.get(
    "/profile",
    responses={200: {"model": Profile}},
)
async def get_profile(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_admin)],
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
    documents = [doc.file for doc in documents]

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
        "avatar": user.avatar_v1,
        "document": documents,
    }

    return Profile(**data)
