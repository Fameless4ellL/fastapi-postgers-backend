from fastapi.testclient import TestClient
import pytest
from models.other import Game, GameType
from schemes.admin import Category, GameViewType
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestGames:
    @pytest.mark.parametrize('game_type', GameType)
    @pytest.mark.parametrize('category', Category)
    @pytest.mark.parametrize('kind', GameViewType)
    @pytest.mark.parametrize('date_from', ['2022-01-01'])
    @pytest.mark.parametrize('date_to', ['2022-01-01'])
    @pytest.mark.parametrize('filter', [None, ''])
    def test_admin_games_is_empty(
        self,
        api: TestClient,
        admin_token: str,
        game_type: str,
        category: str,
        kind: str,
        date_from: str,
        date_to: str,
        filter: str,
    ):
        response = api.get(
            "/v1/admin/games",
            headers={
                "Authorization": f"Bearer {admin_token}",
            },
            params={
                "game_type": game_type.value,
                "category": category.value,
                "kind": kind.value,
                "date_from": date_from,
                "date_to": date_to,
                "filter": filter,
            },
        )
        assert response.status_code == 200
        assert "items" in response.json()
        assert "count" in response.json()

    @pytest.mark.parametrize('game_type', GameType)
    @pytest.mark.parametrize('category', Category)
    @pytest.mark.parametrize('kind', GameViewType)
    @pytest.mark.parametrize('date_from', ['2022-01-01'])
    @pytest.mark.parametrize('date_to', ['2022-01-01'])
    @pytest.mark.parametrize('filter', [None, ''])
    @pytest.mark.usefixtures("game")
    def test_admin_games(
        self,
        api: TestClient,
        admin_token: str,
        game_type: str,
        category: str,
        kind: str,
        date_from: str,
        date_to: str,
        filter: str,
        game: Game,
    ):
        response = api.get(
            "/v1/admin/games",
            headers={
                "Authorization": f"Bearer {admin_token}",
            },
            params={
                "game_type": game_type.value,
                "category": category.value,
                "kind": kind.value,
                "date_from": date_from,
                "date_to": date_to,
                "filter": filter,
            },
        )
        print("/v1/admin/games", response.json(), game.id)
        assert response.status_code == 200
        assert "items" in response.json()
        assert "count" in response.json()
        if response.json()["count"] == 1:
            assert response.json()["items"][0]["id"] == game.id
            assert response.json()["items"][0]["name"] == game.name
            assert response.json()["items"][0]["status"] == game.status
            assert response.json()["items"][0]["kind"] == game.kind
            assert response.json()["items"][0]["country"] == game.country
            assert response.json()["items"][0]["description"] == game.description
