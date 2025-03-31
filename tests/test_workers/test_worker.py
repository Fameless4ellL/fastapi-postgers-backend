import pytest
from models.other import Game
from settings import settings
from utils import proceed_game


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestWorker:
    def test_process_game(self, game: Game):
        proceed_game(game.id)
