import base64
import mimetypes
import os
from typing import Any, Union

from fastapi import HTTPException
from sqlalchemy import select
from starlette import status

from settings import settings
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


def url_for(name: str, **path_params: Any) -> str:
    """
    Generate a URL for the given endpoint name and path parameters.
    """
    return f"{settings.back_url}/{name}/" + "/".join(
        str(value) for value in path_params.values()
    )


def url_for_encoded(name: str, **path_params: Any) -> Union[str, None]:
    """
    Generate an encoded data from file for the given endpoint name and path parameters.
    """
    filename = name + "/" + "/".join(str(value) for value in path_params.values())
    if not os.path.isfile(filename):
        return

    content_type, _ = mimetypes.guess_type(filename)
    if content_type != 'application/pdf':
        return

    with open(filename, "rb") as file:
        encoded = base64.b64encode(file.read()).decode("utf-8")

    return encoded
