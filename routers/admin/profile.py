from fastapi import status, Security
from fastapi.responses import JSONResponse
from typing import Annotated

from models.user import Role, User
from routers import admin
from routers.utils import get_admin, url_for
from schemes.admin import (
    Profile,
)
from schemes.base import BadResponse


@admin.get(
    "/profile",
    responses={
        400: {"model": BadResponse},
        200: {"model": Profile}
    },
)
async def get_profile(
    user: Annotated[User, Security(get_admin, scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ])],
):
    """
    Получение профиля пользователя
    """
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
        content=Profile(**data).model_dump(),
        status_code=status.HTTP_200_OK
    )
