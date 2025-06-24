from fastapi import HTTPException
from sqlalchemy import select
from starlette import status

from src.models import Currency, get_sync_db


def get_currency_by_id(
    currency_id: int
) -> Currency:
    db = next(get_sync_db())
    cur = db.execute(select(Currency).filter(Currency.id == currency_id))
    cur = cur.scalar()

    if cur is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Currency not found"
        )

    return cur.id


def get_first_currency() -> Currency:
    db = next(get_sync_db())
    cur = db.query(Currency).first()

    if cur is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Currency not found"
        )

    return cur.id
