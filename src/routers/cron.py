import datetime
import traceback
from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.db import get_db
from src.models.user import BalanceChangeHistory, Wallet, Balance
from src.models.other import Currency
from src.routers import _cron
from src.globals import q
from worker.worker import worker


class JobRequest(BaseModel):
    func_name: str
    args: list = []
    run_date: datetime.datetime

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Transfer(BaseModel):
    txhash: str
    _from: int
    to: str
    contract: str
    value: float


@_cron.post("/add_job/")
async def add_job(request: JobRequest):
    try:
        func = getattr(worker, request.func_name, None)
        if not func:
            raise ValueError(f"Function {request.func_name} not found")

        q.enqueue_at(
            request.run_date,
            func,
            *request.args,
        )
    except Exception:
        traceback.print_exc()
    return {"status": "ok"}


@_cron.post("/api/transfer/")
async def transfer(
    db: Annotated[AsyncSession, Depends(get_db)],
    item: Transfer
):
    stmt = select(Wallet).where(Wallet.address == item.to)
    wallet = await db.execute(stmt)
    wallet = wallet.scalars().first()

    if not wallet:
        return {"status": "error", "message": "Wallet not found"}

    balance_change_history = await db.execute(
        select(BalanceChangeHistory)
        .filter(BalanceChangeHistory.proof == item.txhash)
    )
    balance_change_history = balance_change_history.scalar()
    if balance_change_history:
        return {"status": "error", "message": "Already processed"}

    stmt = select(Currency).filter(
        Currency.address.ilike(item.contract)
    )
    currency = await db.execute(stmt)
    currency = currency.scalar()

    if not currency or not currency.decimals:
        return {"status": "error", "message": "Currency not found"}

    amount = Decimal(item.value / 10 ** currency.decimals)

    stmt = select(Balance).filter(
        Balance.currency_id == currency.id,
        Balance.user_id == wallet.user_id
    )
    balance = await db.execute(stmt)
    balance = balance.scalar()

    if not balance:
        balance = Balance(
            user_id=wallet.user_id,
            currency_id=currency.id,
            balance=amount
        )
    else:
        balance.balance += amount

    db.add(balance)

    balance_change_history = BalanceChangeHistory(
        user_id=wallet.user_id,
        balance_id=balance.id,
        currency_id=currency.id,
        change_amount=amount,
        change_type="deposit",
        previous_balance=balance.balance - amount,
        status=BalanceChangeHistory.Status.SUCCESS,
        proof=item.txhash,
        new_balance=balance.balance,
        args=item.model_dump_json()
    )
    db.add(balance_change_history)
    await db.commit()

    return {"status": "ok"}


@_cron.get("/hourly")
async def hourly():
    """Часовой отчет по метрикам"""
    q.enqueue(
        worker.calculate_metrics,
        job_id=f"calculate_metrics({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})"
    )
