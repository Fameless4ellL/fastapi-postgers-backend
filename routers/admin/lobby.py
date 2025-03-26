from typing import Annotated
from fastapi import status, Security
from fastapi.responses import JSONResponse

from models.user import Role
from routers import admin
from routers.utils import Token, get_admin_token
from schemes.admin import (
    Profile,
)
from schemes.base import BadResponse


sidebars = {
    Role.SUPPORT.value: [
        'Dashboard',
        "Users",
        "Games",
        "Jackpots",
        "InstaBingo"
        "Statistics",
    ],
    Role.FINANCIER.value: [
        "Dashboard",
        "Users",
        "Games",
        "Jackpots",
        "InstaBingo"
        "Statistics",
        "Referrals",
    ],
    Role.SMM.value: [
        "Referrals",
    ],
    Role.LOCAL_ADMIN.value: [
        "Dashboard",
        "Users",
        "Games",
        "InstaBingo"
        "Statistics",
        "Referrals",
    ],
    Role.GLOBAL_ADMIN.value: [
        "Dashboard",
        "Admins",
        "Users",
        "Games",
        "Jackpots",
        "InstaBingo"
        "Statistics",
        "Referrals",
    ],
    'default': [
        "Dashboard",
        "Admins",
        "Users",
        "Games",
        "Jackpots",
        "InstaBingo"
        "Statistics",
        "Referrals",
        "KYC",
    ]
}


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
    },
)
async def sidebar(
    token: Annotated[Token, Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]),]
):
    """
    Получение информации о боковой панели администратора
    """
    data = sidebars.get(token.role.value, sidebars['default'])

    return JSONResponse(content=data, status_code=status.HTTP_200_OK)
