import pytest
from src.models.other import Game
from src.utils import proceed_game


@pytest.mark.skipif(
    False is True,
    reason="This test is only for debug mode",
)
@pytest.mark.xfail(reason="TODO: Fix this test")
class TestWorker:
    def test_process_game(self, game: Game):
        proceed_game(game.id)
