import uuid
from fastapi import Depends, HTTPException, status, security
from sqlalchemy import select, and_
from models.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User
from models.other import Game, GameInstance, GameStatus, GameType
from utils.signature import decode_access_token


oauth2_scheme = security.OAuth2PasswordBearer(tokenUrl="/v1/login")



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
    if user.role != "admin":
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def generate_game(db: AsyncSession):
    """
    creating a new game instance based on Game
    """
    game = await db.execute(
        select(Game).filter(Game.as_default is True)
    )
    game = game.scalars().first()

    if not game:
        game = Game(
            name=f"game #{str(uuid.uuid4())}",
            game_type=GameType.GLOBAL,
            description="Default game",
            as_default=True
        )

        db.add(game)
        await db.commit()
        await db.refresh(game)

    game_inst = GameInstance(
        game_id=game.id,
        status=GameStatus.PENDING,
    )
    db.add(game_inst)
    await db.commit()
    await db.refresh(game_inst)

    return game_inst, game
