from fastapi import Depends, Path, status, Security
from fastapi.responses import JSONResponse
from typing import Annotated

from sqlalchemy import func, select
from src.models.log import Action
from src.models.user import BalanceChangeHistory, Role, ReferralLink, User
from src.routers import admin
from src.routers.admin import get_crud_router
from src.utils.dependencies import get_admin_token
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.db import get_db
from src.schemes.admin import (
    ReferralFilter,
    ReferralSchema,
    ReferralUsersList,
    Referrals,
    ReferralCreate,
    ReferralUpdate,
)
from src.schemes import BadResponse


get_crud_router(
    model=ReferralLink,
    prefix="/referrals",
    schema=Referrals,
    get_schema=ReferralSchema,
    create_schema=ReferralCreate,
    update_schema=ReferralUpdate,
    filters=Annotated[ReferralFilter, Depends(ReferralFilter)],
    security_scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.SMM.value,
    ],
)


@admin.delete(
    "/referrals/{referral_id}",
    tags=[Action.ADMIN_DELETE],
    dependencies=[Security(get_admin_token, scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.SMM.value,
    ],)],
    responses={
        400: {"model": BadResponse},
    },
)
async def delete_referral(
    db: Annotated[AsyncSession, Depends(get_db)],
    referral_id: Annotated[int, Path(...)]
):
    """
    delete referral
    """
    stmt = select(ReferralLink).filter(ReferralLink.id == referral_id)
    referral = await db.execute(stmt)
    referral = referral.scalar()

    if not referral:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Referral not found"}
        )

    referral.deleted = True
    db.add(referral)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content="Referral deleted",
    )


@admin.get(
    "/referrals/{referral_id}/users",
    dependencies=[Security(get_admin_token, scopes=[
        Role.SUPER_ADMIN.value,
        Role.ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.GLOBAL_ADMIN.value,
        Role.SMM.value,
    ],)],
    responses={
        400: {"model": BadResponse},
        200: {"model": ReferralUsersList},
    },
)
async def get_referral_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    referral_id: Annotated[int, Path(...)],
    offset: int = 0,
    limit: int = 10,
):
    """
    get referral users by referral id
    """
    stmt = (
        select(
            User.id,
            User.username,
            User.country,
            BalanceChangeHistory.change_amount.label("first_deposit"),
            User.created_at,
        )
        .join(BalanceChangeHistory, BalanceChangeHistory.user_id == User.id, isouter=True)
        .filter(User.referral_id == referral_id)
        .order_by(User.id, BalanceChangeHistory.created_at)
        .distinct(User.id)
    )
    result = await db.execute(stmt.offset(offset).limit(limit))
    referral_users = result.fetchall()

    data = [{
        "id": user.id,
        "username": user.username,
        "country": user.country,
        "first_deposit": user.first_deposit,
        "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for user in referral_users]

    count_stmt = select(func.count()).select_from(
        stmt.with_only_columns(User.id).order_by(None).subquery()
    )
    count_result = await db.execute(count_stmt)
    count = count_result.scalar()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ReferralUsersList(
            items=data,
            count=count,
        ).model_dump(),
    )
