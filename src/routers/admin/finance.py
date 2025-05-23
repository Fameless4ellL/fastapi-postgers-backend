import csv
from datetime import datetime
from io import StringIO
from typing import Annotated

from fastapi import Depends, status, Security, Path
from fastapi.responses import JSONResponse
from pytz.tzinfo import DstTzInfo
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.models.db import get_db
from src.models.user import User, Role, BalanceChangeHistory
from src.routers import admin
from src.utils.dependencies import get_admin_token, get_timezone
from src.schemes.admin import (
    Operations,
    OperationFilter,
    Operation,
)
from src.schemes import BadResponse


@admin.get(
    "/operations",
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
        200: {"model": Operations},
    },
)
async def get_operation_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Annotated[OperationFilter, Depends(OperationFilter)],
    timezone: Annotated[DstTzInfo, Depends(get_timezone)],
    export: bool = False,
    offset: int = 0,
    limit: int = 10,
):
    """
    Get operations list
    """
    stmt = (
        select(
            func.json_build_object(
                "id", BalanceChangeHistory.id,
                "user_id", User.id,
                "username", User.username,
                "country", User.country,
                "amount", BalanceChangeHistory.change_amount,
                "transaction_type", BalanceChangeHistory.change_type,
                "status", BalanceChangeHistory.status,
                "created_at", BalanceChangeHistory.created_at,
            ).label("items"),
        )
        .select_from(BalanceChangeHistory)
        .join(User, User.id == BalanceChangeHistory.user_id)
    )

    if item.filter:
        stmt = stmt.where(User.username.ilike(f"%{item.filter}%"))

    if item.status:
        stmt = stmt.where(BalanceChangeHistory.status.in_(item.status))

    if item.countries:
        stmt = stmt.where(User.country.in_(item.countries))

    if item.date_from:
        stmt = stmt.where(BalanceChangeHistory.created_at >= item.date_from)

    if item.date_to:
        stmt = stmt.where(BalanceChangeHistory.created_at <= item.date_to)

    count = stmt.with_only_columns(func.count())
    count = await db.execute(count)
    count = count.scalar()

    stmt = stmt.order_by(*[i.label for i in item.order_by])

    if export:
        result = await db.execute(stmt)
        result = result.scalars().all()

        # Генерация имени файла
        timestamp = timezone.localize(datetime.now()).strftime("%y%m%d_%H%M%S%f")[:-3]
        filename = f"Bingo_operations_{timestamp}.csv"

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "User ID", "Username", "Country", "Amount", "Transaction Type", "Status", "Created At"])
        for row in result:
            writer.writerow([
                row["id"],
                row["user_id"],
                row["username"],
                row["country"],
                row["amount"],
                row["transaction_type"],
                row["status"],
                row["created_at"],
            ])
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    result = result.scalars().all()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Operations(items=result, count=count).model_dump(mode="json"),
    )


@admin.get(
    "/operations/{obj_id}",
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
        200: {"model": Operation},
    },
)
async def get_operation(
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=1)],
):
    """
    Get operation info
    """
    stmt = (
        select(
            func.json_build_object(
                "id", BalanceChangeHistory.id,
                "user_id", User.id,
                "username", User.username,
                "country", User.country,
                "amount", BalanceChangeHistory.change_amount,
                "transaction_type", BalanceChangeHistory.change_type,
                "status", BalanceChangeHistory.status,
                "game_id", BalanceChangeHistory.game_id,
                "count", BalanceChangeHistory.count,
                "created_at", BalanceChangeHistory.created_at
            ).label("items"),
        )
        .select_from(BalanceChangeHistory)
        .join(User, User.id == BalanceChangeHistory.user_id)
        .where(BalanceChangeHistory.id == obj_id)
    )

    result = await db.execute(stmt)
    result = result.scalars().first()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Operation(**result).model_dump(mode="json"),
    )
