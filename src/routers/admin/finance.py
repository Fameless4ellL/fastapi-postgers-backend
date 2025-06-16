import csv
import json
from contextlib import suppress
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from typing import Annotated

from fastapi import Depends, status, Security, Path
from fastapi.responses import JSONResponse
from pytz.tzinfo import DstTzInfo
from rq.exceptions import InvalidJobOperation
from sqlalchemy import func, select, String
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from settings import settings
from src.globals import q
from src.models import Currency
from src.models.db import get_db
from src.models.limit import Limit
from src.models.user import User, Role, BalanceChangeHistory, Balance
from src.routers import admin
from src.schemes import BadResponse
from src.schemes.admin import (
    Operations,
    OperationFilter,
    Operation, Limits, LimitBase, LimitCreate,
)
from src.utils import worker
from src.utils.dependencies import get_admin_token, get_timezone, Token


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
    limit: int = 12,
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
                "sum", BalanceChangeHistory.change_amount,
                "amount", BalanceChangeHistory.count,
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

    if item.type:
        stmt = stmt.where(BalanceChangeHistory.change_type.in_([i.label for i in item.type]))

    if item.date_from:
        stmt = stmt.where(BalanceChangeHistory.created_at >= item.date_from)

    if item.date_to:
        to_the_end_date = datetime.combine(item.date_to, datetime.min.time()) + timedelta(hours=23, minutes=59)
        stmt = stmt.where(BalanceChangeHistory.created_at <= to_the_end_date)

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
                "sum", BalanceChangeHistory.change_amount,
                "amount", BalanceChangeHistory.count,
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


@admin.get(
    "/limits",
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
        200: {"model": Limits},
    },
)
async def get_limit_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: int = 0,
    limit: int = 10,
):
    """
    Пользователь должен иметь возможность просмотра списка лимитов,
    чтобы иметь представление об активных лимитах и управлять ими.
    """
    stmt = (
        select(
            func.json_build_object(
                "id", Limit.id,
                "type", func.lower(Limit.type.cast(String)),
                "value", Limit.value,
                "currency", Currency.code,
                "operation_type", func.lower(Limit.operation_type.cast(String)),
                "period", func.lower(Limit.period.cast(String)),
                "kyc", Limit.kyc,
                "status", func.lower(Limit.status.cast(String)),
                "risk", func.lower(Limit.risk.cast(String)),
                "is_deleted", Limit.is_deleted,
                "created_at", Limit.created_at,
                "updated_at", Limit.updated_at,
                "last_edited", Limit.last_edited,
            )
        )
        .select_from(Limit)
        .join(Currency, Currency.id == Limit.currency_id)
    )
    count = stmt.with_only_columns(func.count())
    count = await db.execute(count)
    count = count.scalar()

    stmt = stmt.order_by(Limit.status.asc(), Limit.created_at.desc())
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    result = result.scalars().all()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=Limits(items=result, count=count).model_dump(mode="json"),
    )


@admin.get(
    "/limits/{obj_id}",
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
        200: {"model": LimitBase},
    },
)
async def get_limit(
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=1)],
):
    stmt = (
        select(
            func.json_build_object(
                "id", Limit.id,
                "type", func.lower(Limit.type.cast(String)),
                "value", Limit.value,
                "currency", Currency.code,
                "operation_type", func.lower(Limit.operation_type.cast(String)),
                "period", func.lower(Limit.period.cast(String)),
                "kyc", Limit.kyc,
                "status", func.lower(Limit.status.cast(String)),
                "risk", func.lower(Limit.risk.cast(String)),
                "created_at", Limit.created_at,
                "is_deleted", Limit.is_deleted,
                "updated_at", Limit.updated_at,
                "last_edited", Limit.last_edited,
            )
        )
        .select_from(Limit)
        .join(Currency, Currency.id == Limit.currency_id)
        .where(Limit.id == obj_id)
    )
    result = await db.execute(stmt)
    result = result.scalars().first()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=LimitBase(**result).model_dump(mode="json"),
    )


@admin.post(
    "/limit",
    responses={
        400: {"model": BadResponse},
        200: {"model": LimitBase},
    },
)
async def create_limit(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[Token, Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]),],
    item: LimitCreate
):

    currency = await db.execute(select(Currency))
    currency = currency.scalars().first()

    limit = Limit(**item.model_dump())
    limit.currency_id = currency.id
    limit.last_edited = token.id

    db.add(limit)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content="Limit created successfully",
    )


@admin.put(
    "/limits/{obj_id}",
    responses={
        400: {"model": BadResponse},
        200: {"model": LimitBase},
    },
)
async def update_limit(
    token: Annotated[Token, Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]),],
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=1)],
    item: LimitCreate
):
    stmt = (
        select(Limit)
        .where(Limit.id == obj_id)
    )
    result = await db.execute(stmt)
    result = result.scalars().first()

    if not result:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Limit not found"},
        )

    for attr, value in item.model_dump().items():
        setattr(result, attr, value)

    result.last_edited = token.id

    db.add(result)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content="Limit updated successfully",
    )


@admin.delete(
    "/limits/{obj_id}",
    responses={
        400: {"model": BadResponse},
        200: {"model": LimitBase},
    },
)
async def delete_limit(
    token: Annotated[Token, Security(get_admin_token, scopes=[
        Role.GLOBAL_ADMIN.value,
        Role.ADMIN.value,
        Role.SUPER_ADMIN.value,
        Role.LOCAL_ADMIN.value,
        Role.FINANCIER.value,
        Role.SUPPORT.value
    ]),],
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=1)],
):
    stmt = (
        select(Limit)
        .where(Limit.id == obj_id)
    )
    result = await db.execute(stmt)
    result = result.scalars().first()

    if not result:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Limit not found"},
        )

    if result.is_deleted:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Cannot delete deleted item"},
        )

    result.is_deleted = True
    result.last_edited = token.id
    db.add(result)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content="Limit updated successfully",
    )


@admin.post(
    "/operation/block/user/{obj_id}",
    responses={
        400: {"model": BadResponse},
        200: {"model": dict},
    },
)
async def block_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=1)],
    penalty_amount: float,
):
    """
    Block a user based on suspicious operations.
    """
    # Fetch user and wallet details
    user_stmt = select(User).where(User.id == obj_id)
    user = await db.execute(user_stmt)
    user = user.scalars().first()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "User not found"},
        )

    if user.is_blocked:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User is already blocked"},
        )

    balance_stmt = select(Balance).where(Balance.user_id == obj_id)
    balance = await db.execute(balance_stmt)
    balance = balance.scalars().first()

    if not balance:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Balance not found"},
        )

    currency = await db.execute(
        select(Currency)
    )
    currency = currency.scalars().first()

    operations_stmt = (
        select(BalanceChangeHistory)
        .where(
            BalanceChangeHistory.user_id == obj_id,
            BalanceChangeHistory.status == BalanceChangeHistory.Status.PENDING
        )
    )
    operations = await db.execute(operations_stmt)
    operations = operations.scalars().all()

    total_operation_amount = 0
    for op in operations:
        job = q.fetch_job(f"{op.change_type}_{op.id}")

        if job and job.is_finished:
            # If the job is finished, we can skip this operation
            continue

        with suppress(InvalidJobOperation, AttributeError):
            job.cancel()

        op.status = BalanceChangeHistory.Status.BLOCKED
        total_operation_amount += op.change_amount
        db.add(op)

    if total_operation_amount >= penalty_amount:
        # если сумма операции больше либо равна сумме установленного штрафа,
        # то формирует операцию типа Штраф "penalty",
        # вычитая сумму штрафа из суммы транзакции(ий),
        # ставших причиной блокировки.

        penalty = total_operation_amount - penalty_amount
        total_operation_amount -= penalty

        previous_balance = balance.balance
        balance.balance -= Decimal(penalty)

        balance_change_history = BalanceChangeHistory(
            user_id=obj_id,
            balance_id=balance.id,
            currency_id=currency.id,
            change_amount=-penalty,
            change_type="penalty",
            previous_balance=previous_balance,
            status=BalanceChangeHistory.Status.PENDING,
            new_balance=balance.balance,
            args=json.dumps({"address": settings.address})
        )
        db.add(balance_change_history)
        await db.commit()
        await db.refresh(balance_change_history)

        q.enqueue(
            worker.withdraw,
            history_id=balance_change_history.id,
        )

    elif balance.balance >= penalty_amount:
        # если сумма операции меньше суммы штрафа,
        # но баланс кошелька больше либо равен сумме штрафа,
        # то формирует операцию типа Штраф "penalty",
        # вычитая сумму штрафа из суммы транзакции(ий),
        # ставших причиной блокировки.

        penalty = penalty_amount
        previous_balance = balance.balance
        balance.balance -= Decimal(penalty)
        balance_change_history = BalanceChangeHistory(
            user_id=obj_id,
            balance_id=balance.id,
            currency_id=currency.id,
            change_amount=-penalty,
            change_type="penalty",
            previous_balance=previous_balance,
            status=BalanceChangeHistory.Status.PENDING,
            new_balance=balance.balance,
            args=json.dumps({"address": settings.address})
        )
        db.add(balance_change_history)
        await db.commit()
        await db.refresh(balance_change_history)

        q.enqueue(
            worker.withdraw,
            history_id=balance_change_history.id,
        )

    if total_operation_amount > 0:
        # If there are remaining funds after penalty deduction,
        # transfer them to the user's wallet.
        first_deposit = await db.execute(
            select(BalanceChangeHistory)
            .where(
                BalanceChangeHistory.user_id == obj_id,
                BalanceChangeHistory.change_type == "deposit",
                BalanceChangeHistory.status == BalanceChangeHistory.Status.SUCCESS
            )
            .order_by(BalanceChangeHistory.created_at.asc())
        )
        first_deposit = first_deposit.scalars().first()

        if first_deposit:
            args = json.loads(first_deposit.args or "{}")
            address = args.get("address", None)

            if address:
                # Create a new withdrawal operation
                deposit = BalanceChangeHistory(
                    user_id=obj_id,
                    balance_id=balance.id,
                    currency_id=currency.id,
                    change_amount=-total_operation_amount,
                    change_type="withdraw",
                    previous_balance=balance.balance,
                    status=BalanceChangeHistory.Status.PENDING,
                    new_balance=balance.balance,
                    args=json.dumps({"address": address})
                )
                db.add(deposit)

                q.enqueue(
                    worker.withdraw,
                    history_id=deposit.id,
                )

    user.is_blocked = True
    db.add(user)
    db.add(balance)

    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "User blocked successfully"},
    )


@admin.post(
    "/operation/block/{obj_id}",
    responses={
        400: {"model": BadResponse},
        200: {"model": dict},
    },
)
async def block_operation(
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=1)],
):
    stmt = (
        select(BalanceChangeHistory)
        .where(
            BalanceChangeHistory.id == obj_id,
            BalanceChangeHistory.status == BalanceChangeHistory.Status.PENDING
        )
    )
    op = await db.execute(stmt)
    op = op.scalars().first()

    if not op:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "PENDING Operation not found"},
        )

    job = q.fetch_job(f"{op.change_type}_{op.id}")

    if job.is_finished:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "Operation already finished"},
        )

    with suppress(InvalidJobOperation, AttributeError):
        job.cancel()

    op.status = BalanceChangeHistory.Status.BLOCKED
    db.add(op)
    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Operation blocked successfully"},
    )


@admin.post(
    "/operation/unblock/user/{obj_id}",
    responses={
        400: {"model": BadResponse},
        200: {"model": dict},
    },
)
async def unblock_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=1)],
):
    """
    Unblock a user
    """
    # Fetch user and wallet details
    user_stmt = select(User).where(User.id == obj_id)
    user = await db.execute(user_stmt)
    user = user.scalars().first()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "User not found"},
        )

    if not user.is_blocked:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"message": "User is already unblocked"},
        )

    user.is_blocked = False
    db.add(user)

    await db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "User unblocked successfully"},
    )