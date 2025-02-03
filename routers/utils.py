from itertools import islice
from typing import Any
import uuid
from fastapi import Depends, HTTPException, status, security
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from models.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User
from models.other import Game, GameInstance, GameStatus, GameType
from utils.signature import decode_access_token
from settings import settings
from globals import scheduler
from utils.workers import add_job_to_scheduler


oauth2_scheme = security.OAuth2PasswordBearer(tokenUrl="/v1/token")


async def get_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    phone_number = payload.get("sub", "")
    username = payload.get("username", "")

    if phone_number is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user = await db.execute(
        select(User)
        .filter(and_(
            User.phone_number == phone_number,
            User.username == username
        ))
    )
    user = user.scalar()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


async def get_admin(
    user: User = Depends(get_user)
) -> User:
    # if user.role != "admin":
    #     raise HTTPException(status_code=404, detail="User not found")
    return user


async def generate_game(db: AsyncSession, _type: GameType = GameType.GLOBAL):
    """
    creating a new game instance based on Game
    """
    game = await db.execute(
        select(Game).filter(
            Game.repeat.is_(True),
            Game.game_type == _type
        )
    )
    game = game.scalars().first()

    if not game:
        game = Game(
            name=f"game #{str(uuid.uuid4())}",
            game_type=_type,
            description="Default game",
            repeat=True,
            repeat_days=[0, 1, 2, 3, 4, 5, 6],
            scheduled_datetime=datetime.now() + timedelta(days=1)
        )

        db.add(game)
        await db.commit()
        await db.refresh(game)

    game_inst = GameInstance(
        game_id=game.id,
        status=GameStatus.PENDING,
        scheduled_datetime=game.scheduled_datetime
    )
    db.add(game_inst)
    await db.commit()
    await db.refresh(game_inst)

    add_job_to_scheduler(
        "add_to_queue",
        ["proceed_game", game_inst.id],
        game.scheduled_datetime
    )

    return game_inst, game


def nth(iterable, n, default=None):
    "Returns the nth item or a default value."
    return next(islice(iterable, n, None), default)


def url_for(name: str, **path_params: Any) -> str:
    """
    Generate a URL for the given endpoint name and path parameters.
    """
    return f"{settings.back_url}/{name}/" + "/".join(
        str(value) for value in path_params.values()
    )
