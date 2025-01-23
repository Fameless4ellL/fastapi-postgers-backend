import uuid
from sqlalchemy import select
from models.db import get_sync_db
from models.other import Game, GameInstance, GameStatus, GameType
from globals import worker
from sqlalchemy import select
from models.other import Game, GameInstance, GameStatus


@worker.register
def generate_game():
    """
    creating a new game instance based on Game
    """
    db = get_sync_db()
    game = db.execute(
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
        db.commit()
        db.refresh(game)

    game_inst = GameInstance(
        game_id=game.id,
        status=GameStatus.PENDING,
    )
    db.add(game_inst)
    db.commit()
    db.refresh(game_inst)

    return True


@worker.register
def proceed_game(game_id: int):
    """
    розыгрыш - выйгрышная комбинация
    """
    db = get_sync_db()
    game = db.execute(
        select(Game).filter(Game.id == game_id)
    )
    
    return True