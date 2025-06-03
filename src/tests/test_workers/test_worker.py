import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.globals import q
from src.models.other import Game, GameStatus, Jackpot
from src.utils import proceed_game, set_pending_jackpot


@pytest.mark.xfail(reason="TODO: Fix this test")
class TestWorker:
    def test_process_game(self, game: Game):
        proceed_game(game.id)


class TestQueue:
    @pytest.mark.xfail(reason="can't update queue")
    async def test_queue(
        self,
        async_api,
        db: AsyncSession,
        jackpot: Jackpot,
    ):
        job = q.enqueue_at(
            datetime=datetime.now() + timedelta(seconds=1),
            f=set_pending_jackpot,
            jackpot_id=jackpot.id,
            status=GameStatus.ACTIVE,
            job_id=f"test_set_pending_jackpot_{jackpot.id}"
        )

        assert job is not None
        await asyncio.sleep(1)

        game = await db.execute(
            select(Jackpot).where(Jackpot.id == jackpot.id)
        )
        game = game.scalars().first()
        assert game is not None
        assert game.status == GameStatus.ACTIVE
