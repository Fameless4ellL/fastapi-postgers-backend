import pytest
from fastapi import status
from httpx import AsyncClient

from src.models.user import User


class TestUser:
    @pytest.mark.xfail(reason="Not implemented yet")
    async def test_withdraw(
        self,
        async_api: AsyncClient,
        token: str,
    ):
        response = await async_api.post(
            "/v1/withdraw",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        print(response.json())

    async def test_upload(
        self,
        async_api: AsyncClient,
        token: str,
    ):
        response = await async_api.post(
            "/v1/upload",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        print(response.json())

    async def test_profile(
        self,
        async_api: AsyncClient,
        token: str,
    ):
        response = await async_api.get(
            "/v1/profile",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        print(response.json())

    async def test_mygames(
        self,
        async_api: AsyncClient,
        token: str,
    ):
        response = await async_api.get(
            "/v1/mygames",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        print(response.json())

    async def test_history(
        self,
        async_api: AsyncClient,
        token: str,
    ):
        response = await async_api.get(
            "/v1/history",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        print(response.json())

    async def test_countries(
        self,
        async_api: AsyncClient,
        token: str,
    ):
        response = await async_api.get(
            "/v1/countries",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        print(response.json())

    async def test_balance(
        self,
        async_api: AsyncClient,
        token: str,
    ):
        response = await async_api.get(
            "/v1/balance",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(response.json())
        assert response.status_code == status.HTTP_200_OK

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
