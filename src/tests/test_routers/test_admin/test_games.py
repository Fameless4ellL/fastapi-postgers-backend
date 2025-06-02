import pytest
from httpx import AsyncClient

from src.models.other import Game, GameType, Ticket
from src.models.user import User
from src.schemes.admin import Category, GameView


class TestGames:
    @pytest.mark.parametrize('game_type', GameType)
    @pytest.mark.parametrize('category', Category)
    @pytest.mark.parametrize('kind', GameView)
    @pytest.mark.parametrize('date_from', ['2022-01-01'])
    @pytest.mark.parametrize('date_to', ['2022-01-01'])
    @pytest.mark.parametrize('_filter', [None, ''])
    async def test_admin_games_is_empty(
        self,
        async_api: AsyncClient,
        admin_token: str,
        game_type: str,
        category: str,
        kind: str,
        date_from: str,
        date_to: str,
        _filter: str,
    ):
        response = await async_api.get(
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
                "filter": _filter,
            },
        )
        assert response.status_code == 200
        assert "items" in response.json()
        assert "count" in response.json()

    @pytest.mark.parametrize('game_type', GameType)
    @pytest.mark.parametrize('category', Category)
    @pytest.mark.parametrize('kind', GameView)
    @pytest.mark.parametrize('date_from', ['2022-01-01'])
    @pytest.mark.parametrize('date_to', ['2022-01-01'])
    @pytest.mark.parametrize('_filter', [None, ''])
    @pytest.mark.usefixtures("game")
    async def test_admin_games(
        self,
        async_api: AsyncClient,
        admin_token: str,
        game_type: str,
        category: str,
        kind: str,
        date_from: str,
        date_to: str,
        _filter: str,
        game: Game,
    ):
        response = await async_api.get(
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
                "filter": _filter,
            },
        )
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

    @pytest.mark.parametrize('_type', ['delete', 'cancel'])
    async def test_delete_game(
        self,
        async_api: AsyncClient,
        admin_token: str,
        _type: str,
        game: Game,
    ):
        response = await async_api.delete(
            f"/v1/admin/games/{game.id}",
            headers={
                "Authorization": f"Bearer {admin_token}",
            },
            params={
                "_type": _type,
            },
        )
        assert response.status_code == 200
        assert response.json() == "Success"

    async def test_get_purchased_tickets(
        self,
        async_api: AsyncClient,
        admin_token: str,
        game: Game,
        ticket: Ticket
    ):
        response = await async_api.get(
            f"/v1/admin/games/{game.id}/purchased",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 200

    async def test_get_participants(
        self,
        async_api: AsyncClient,
        admin_token: str,
        game: Game,
        ticket: Ticket
    ):
        response = await async_api.get(
            f"/v1/admin/games/{game.id}/participants",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 200

    async def test_get_participant_tickets(
        self,
        async_api: AsyncClient,
        admin_token: str,
        user: User,
        game: Game,
        ticket: Ticket
    ):
        response = await async_api.get(
            f"/v1/admin/games/{game.id}/participants/{user.id}",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 200

    async def test_get_winners(
        self,
        async_api: AsyncClient,
        admin_token: str,
        game: Game,
        ticket_winner: Ticket
    ):
        response = await async_api.get(
            f"/v1/admin/games/{game.id}/winners",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 200

        data = response.json()
        assert "items" in data.keys()
        assert "count" in data.keys()

        assert data["count"] == 1
        assert data["items"][0]["id"] == ticket_winner.id
        assert data["items"][0]["user_id"] == ticket_winner.user_id
        assert data["items"][0]["numbers"] == ticket_winner.number
        assert data["items"][0]["amount"] == ticket_winner.amount
        assert data["items"][0]["status"] == ticket_winner.status.value

    async def test_set_ticket_status(
        self,
        async_api: AsyncClient,
        admin_token: str,
        game: Game,
        ticket: Ticket
    ):
        response = await async_api.put(
            f"/v1/admin/games/{game.id}/winners/{ticket.id}",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 200 if game.kind == GameView.MATERIAL else 400
