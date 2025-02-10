from functools import wraps
from itertools import islice
from typing import Annotated, Any
import uuid
from fastapi import Depends, HTTPException, status, security
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from models.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User, Role
from models.other import Game, GameInstance, GameStatus, GameType
from utils.signature import decode_access_token
from settings import settings
from globals import scheduler
from utils.workers import add_to_queue


oauth2_scheme = security.OAuth2PasswordBearer(tokenUrl="/v1/token")
admin_oauth2_scheme = security.OAuth2PasswordBearer(tokenUrl="/v1/token")


async def get_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
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
    token: Annotated[str, Depends(admin_oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    password = payload.get("password", "")
    username = payload.get("username", "")

    if password is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user = await db.execute(
        select(User)
        .filter(User.username == username)
    )
    user = user.scalar()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


async def generate_game(
    db: AsyncSession,
    _type: GameType = GameType.GLOBAL,
    country: str = None
):
    """
    creating a new game instance based on Game
    """
    game = await db.execute(
        select(Game).filter(
            Game.repeat.is_(True),
            Game.game_type == _type,
            Game.country == country
        )
    )
    game = game.scalars().first()

    if not game:
        game = Game(
            name=f"game #{str(uuid.uuid4())}",
            game_type=_type,
            description="Default game",
            country=country,
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

    scheduler.add_job(
        func=add_to_queue,
        trigger="date",
        args=["proceed_game", game_inst.id],
        run_date=game.scheduled_datetime
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


def permission(allowed_roles: list[Role]):
    async def dependency(user: Annotated[User, Depends(get_admin)]):
        if user.role not in allowed_roles + [Role.SUPER_ADMIN.value]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )
        return user
    return dependency
