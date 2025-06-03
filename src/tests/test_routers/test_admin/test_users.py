from httpx import AsyncClient
from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import User, Game, Currency


class TestAdminUsers:
    async def test_retrieves_users_list(
        self,
        async_api: AsyncClient,
        admin_token: str,
    ):
        response = await async_api.get(
            "v1/admin/users?offset=0&limit=10",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "users" in response.json()
        assert "count" in response.json()

    async def test_retrieves_users_list_with_query(
        self,
        async_api: AsyncClient,
        admin_token: str,
    ):
        response = await async_api.get(
            "v1/admin/users?query=test&offset=0&limit=10",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "users" in response.json()
        assert "count" in response.json()

    async def test_retrieves_user_details(
        self,
        db: AsyncSession,
        async_api: AsyncClient,
        admin_token: str,
    ):
        user = User(
            phone_number="77079898999",
            username="test_user3",
            country="KAZ",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        response = await async_api.get(
            f"v1/admin/users/{user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["id"] == user.id

        await db.delete(user)

    async def test_retrieves_user_details_not_found(
        self,
        async_api: AsyncClient,
        admin_token: str,
    ):
        response = await async_api.get(
            "v1/admin/users/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["message"] == "User not found"

    async def test_retrieves_user_games(
        self,
        async_api: AsyncClient,
        admin_token: str,
        user: User
    ):
        response = await async_api.get(
            f"v1/admin/users/{user.id}/games?offset=0&limit=10",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "games" in response.json()
        assert "count" in response.json()

    async def test_retrieves_user_games_not_found(
        self,
        async_api: AsyncClient,
        admin_token: str,
    ):
        response = await async_api.get(
            "v1/admin/users/99999/games?offset=0&limit=10",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["message"] == "User not found"

    async def test_retrieves_user_tickets(
        self,
        async_api: AsyncClient,
        admin_token: str,
        user: User,
        game: Game
    ):
        response = await async_api.get(
            f"v1/admin/users/{user.id}/games/{game.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "tickets" in response.json()
        assert "count" in response.json()

    async def test_retrieves_user_tickets_not_found(
        self,
        async_api: AsyncClient,
        admin_token: str,
    ):
        response = await async_api.get(
            "v1/admin/users/99999/games/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_retrieves_user_balance(
        self,
        async_api: AsyncClient,
        admin_token: str,
        user: User
    ):
        response = await async_api.get(
            f"v1/admin/users/{user.id}/balance",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "balances" in response.json()
        assert "total" in response.json()

    async def test_retrieves_user_balance_not_found(
        self,
        async_api: AsyncClient,
        db: AsyncSession,
        admin_token: str,
    ):
        response = await async_api.get(
            "v1/admin/users/99999/balance",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK

        count = await db.execute(
            select(func.count()).select_from(Currency)
        )

        assert len(response.json()["balances"]) == count.scalar()
        assert int(response.json()["total"]) == 0
