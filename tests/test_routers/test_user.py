from fastapi import status
from httpx import AsyncClient

from models.user import User


class TestUser:
    async def test_tickets(
        self,
        async_api: AsyncClient,
        token: str,
    ):
        response = await async_api.get(
            "/v1/tickets",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"tickets": [], "count": 0}

    async def test_get_notifications(
        self,
        async_api: AsyncClient,
        token: str,
    ):
        response = await async_api.get(
            "/v1/notifications",
            headers={
                "Authorization": f"Bearer {token}",
            }
        )
        assert response.status_code == 200

    async def test_set_settings(
        self,
        async_api: AsyncClient,
        token: str,
        user: User,
    ):
        response = await async_api.post(
            "/v1/settings",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "locale": "EN",
                "country": "USA",
            }
        )
        assert response.status_code == 200
