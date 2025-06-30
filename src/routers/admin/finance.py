import csv
import json
from contextlib import suppress
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from typing import Annotated

from fastapi import Depends, Path, APIRouter
from pytz.tzinfo import DstTzInfo
from rq.exceptions import InvalidJobOperation
from sqlalchemy import func, select, String, not_
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from settings import settings
from src.exceptions.balance import BalanceExceptions
from src.exceptions.limit import LimitExceptions
from src.exceptions.operation import HistoryExceptions
from src.exceptions.user import UserExceptions
from src.globals import q
from src.models import Currency
from src.models.db import get_db
from src.models.limit import Limit
from src.models.user import User, BalanceChangeHistory, Balance
from src.schemes.admin import (
    Operations,
    OperationFilter,
    Operation, Limits, LimitBase, LimitCreate,
)
from src.utils import worker
from src.utils.dependencies import get_timezone, Token, JWTBearerAdmin


finance = APIRouter(tags=["v1.admin.finance"])


@finance.get(
    "/operations",
    responses={200: {"model": Operations}},
)
async def get_operation_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Annotated[OperationFilter, Depends(OperationFilter)],
    timezone: Annotated[DstTzInfo, Depends(get_timezone)],
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
                "user_is_blocked", func.coalesce(User.is_blocked, False),
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
        .filter(BalanceChangeHistory.status != BalanceChangeHistory.Status.BLOCKED)
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

    if item.export:
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

    return Operations(items=result, count=count)


@finance.get(
    "/operations/{obj_id}",
    responses={200: {"model": Operation}},
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

    await HistoryExceptions.operation_not_found(result)

    return Operation(**result)


@finance.get(
    "/limits",
    responses={200: {"model": Limits}},
)
async def get_limit_list(
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: int = 0,
    limit: int = 12,
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
                "operation_type", Limit.operation_type,
                "period", func.lower(Limit.period.cast(String)),
                "kyc", Limit.kyc,
                "status", not_(Limit.is_deleted),
                "risk", func.lower(Limit.risk.cast(String)),
                "created_at", Limit.created_at,
                "updated_at", Limit.updated_at,
                "last_editer", Limit.last_edited,
            )
        )
        .select_from(Limit)
        .join(Currency, Currency.id == Limit.currency_id)
    )
    count = stmt.with_only_columns(func.count())
    count = await db.execute(count)
    count = count.scalar()

    stmt = stmt.order_by(Limit.is_deleted.asc(), Limit.created_at.desc())
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    result = result.scalars().all()

    return Limits(items=result, count=count)


@finance.get(
    "/limits/{obj_id}",
    response_model=LimitBase,
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
                "operation_type", Limit.operation_type,
                "period", func.lower(Limit.period.cast(String)),
                "kyc", Limit.kyc,
                "status", not_(Limit.is_deleted),
                "risk", func.lower(Limit.risk.cast(String)),
                "created_at", Limit.created_at,
                "updated_at", Limit.updated_at,
                "last_editer", Limit.last_edited,
            )
        )
        .select_from(Limit)
        .join(Currency, Currency.id == Limit.currency_id)
        .filter(Limit.id == obj_id)
    )
    result = await db.execute(stmt)
    result = result.scalars().first()

    await LimitExceptions.limit_not_found(result)

    return result


@finance.post("/limit")
async def create_limit(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[Token, Depends(JWTBearerAdmin())],
    item: LimitCreate
):

    currency = await db.execute(select(Currency))
    currency = currency.scalars().first()

    limit = Limit(**item.model_dump())
    limit.currency_id = currency.id
    limit.last_edited = token.id

    db.add(limit)
    await db.commit()

    return "Limit created successfully"


@finance.put("/limits/{obj_id}")
async def update_limit(
    token: Annotated[Token, Depends(JWTBearerAdmin())],
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

    await LimitExceptions.limit_not_found(result)

    for attr, value in item.model_dump().items():
        setattr(result, attr, value)

    result.last_edited = token.id

    db.add(result)
    await db.commit()

    return "Limit updated successfully"


@finance.patch("/limits/{obj_id}")
async def set_status_limit(
    token: Annotated[Token, Depends(JWTBearerAdmin())],
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=1)],
):
    stmt = (
        select(Limit)
        .filter(Limit.id == obj_id)
    )
    result = await db.execute(stmt)
    result = result.scalars().first()

    await LimitExceptions.limit_not_found(result)

    result.is_deleted = not result.is_deleted
    result.last_edited = token.id
    db.add(result)
    await db.commit()

    return "Limit updated successfully"


@finance.post("/operation/block/user/{obj_id}")
async def block_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    obj_id: Annotated[int, Path(ge=1)],
    penalty_amount: float,
):
    """
    Block a user based on suspicious operations.
    """
    # Fetch user and wallet details
    user_stmt = (
        select(User)
        .filter(User.id == obj_id)
    )
    user = await db.execute(user_stmt)
    user = user.scalars().first()

    await UserExceptions.raise_exception_user_not_found(user)
    await UserExceptions.user_is_blocked(user)

    balance_stmt = select(Balance).where(Balance.user_id == obj_id)
    balance = await db.execute(balance_stmt)
    balance = balance.scalars().first()

    await BalanceExceptions.balance_not_found(balance)

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

        with suppress(InvalidJobOperation, AttributeError):
            if job.is_finished:
                # If the job is finished, we can skip this operation
                continue

            job.cancel()

        op.status = BalanceChangeHistory.Status.BLOCKED
        total_operation_amount += op.change_amount
        db.add(op)

    if total_operation_amount >= penalty_amount:
        # если сумма операции больше либо равна сумме установленного штрафа,
        # то формирует операцию типа Штраф "penalty",
        # вычитая сумму штрафа из суммы транзакции(ий),
        # ставших причиной блокировки.

        penalty = total_operation_amount - Decimal(penalty_amount)
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

    return {"message": "User blocked successfully"}


@finance.post("/operation/block/{obj_id}")
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
    await HistoryExceptions.operation_not_found(op)

    job = q.fetch_job(f"{op.change_type}_{op.id}")

    with suppress(InvalidJobOperation, AttributeError):
        await HistoryExceptions.operation_is_finished(job)
        job.cancel()

    op.status = BalanceChangeHistory.Status.BLOCKED
    db.add(op)
    await db.commit()

    return {"message": "Operation blocked successfully"}


@finance.post("/operation/unblock/user/{obj_id}")
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

    await UserExceptions.raise_exception_user_not_found(user)

    user.is_blocked = not user.is_blocked
    db.add(user)

    await db.commit()

    return {"message": "User unblocked successfully"}
