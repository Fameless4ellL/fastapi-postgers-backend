from fastapi import status, Security
from fastapi.responses import JSONResponse

from models.user import Role
from routers import admin
from routers.utils import get_admin_token
from schemes.admin import (
    Profile,
)
from schemes.base import BadResponse


@admin.get(
    "/sidebar",
    dependencies=[Security(
        get_admin_token,
        scopes=[
            Role.SUPER_ADMIN.value,
            Role.ADMIN.value,
            Role.GLOBAL_ADMIN.value,
            Role.LOCAL_ADMIN.value,
            Role.FINANCIER.value,
            Role.SUPPORT.value
        ])],
    responses={
        400: {"model": BadResponse},
        200: {"model": Profile}
    },
)
async def get_profile():
    """
    Получение информации о боковой панели администратора
    """
    data = {
        "Dashboard": {
            "status": "active",
        },
        "Admins": {
            "status": "active",
        },
        "Users": {
            "status": "active",
        },
        "Games": {
            "status": "active",
        },
        "InstaBingo": {
            "status": "active",
        },
        "Jackpots": {
            "status": "active",
        },
        "Statistics": {
            "status": "active",
        },
        "Referrals": {
            "status": "active",
        },
        "KYC": {
            "status": "active",
        },
    }

    return JSONResponse(content=data, status_code=status.HTTP_200_OK)
