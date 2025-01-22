import uuid
from fastapi import Depends, HTTPException
from sqlalchemy import select
from models.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User
from models.other import Game, GameInstance, GameStatus, GameType


async def get_user(
    telegram_id: int,
    db: AsyncSession = Depends(get_db)
) -> User:
    result = await db.execute(
        select(User).filter(User.telegram_id == telegram_id)
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def get_admin(
    user: User = Depends(get_user)
) -> User:
    if not user:
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
