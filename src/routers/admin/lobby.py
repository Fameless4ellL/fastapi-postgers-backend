from typing import Annotated
from fastapi import status, Depends
from fastapi.responses import JSONResponse

from src.models.user import Role
from src.routers import admin
from src.utils.dependencies import Token, JWTBearerAdmin

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


@admin.get("/sidebar")
async def sidebar(token: Annotated[Token, Depends(JWTBearerAdmin())]):
    """
    Получение информации о боковой панели администратора
    """
    role = next(iter(token.scopes))
    data = sidebars.get(role, sidebars['default'])

    return JSONResponse(content=data, status_code=status.HTTP_200_OK)
