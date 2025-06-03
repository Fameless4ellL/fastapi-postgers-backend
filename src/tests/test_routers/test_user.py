import json

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Currency, Network
from src.models.user import User, Balance, Notification
from src.schemes import MyGamesType


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

    @pytest.mark.xfail(reason="422")
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

    @pytest.mark.parametrize("game", MyGamesType)
    async def test_mygames(
        self,
        async_api: AsyncClient,
        token: str,
        game: MyGamesType
    ):
        response = await async_api.get(
            "/v1/mygames",
            params={"item": game.value},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK

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

    @pytest.mark.parametrize("q", ["", "test", "example"])
    async def test_countries(
        self,
        async_api: AsyncClient,
        token: str,
        q: str,
    ):
        response = await async_api.get(
            "/v1/countries",
            params={"q": q},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_balance(
        self,
        db: AsyncSession,
        async_api: AsyncClient,
        token: str,
    ):
        response = await async_api.get(
            "/v1/balance",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK

        items = response.json()['items']
        assert isinstance(items, list)

        for item in items:
            assert isinstance(item, dict)
            assert 'id' in item
            assert 'balance' in item
            assert 'currency' in item
            assert 'network' in item

            balance = select(Balance).where(Balance.id == item['id'])
            balance = await db.execute(balance)
            balance = balance.scalar_one_or_none()
            assert balance is not None
            assert item['balance'] == balance.balance

            currency = select(Currency).where(Currency.id == balance.currency_id)
            currency = await db.execute(currency)
            currency = currency.scalar_one_or_none()
            assert currency is not None
            assert item['currency'] == currency.code

            network = select(Network).where(Network.id == currency.network_id)
            network = await db.execute(network)
            network = network.scalar_one_or_none()
            assert network is not None
            assert item['network'] == network.symbol

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
        notification: Notification
    ):
        response = await async_api.get(
            "/v1/notifications",
            headers={
                "Authorization": f"Bearer {token}",
            }
        )
        assert response.status_code == 200
        data = response.json()

        assert "items" in data.keys()
        assert "count" in data.keys()

        assert data["items"][0]["id"] == notification.id
        assert data["items"][0]["head"] == notification.head
        assert data["items"][0]["body"] == notification.body
        assert data["items"][0]["args"] == json.loads(notification.args)

    async def test_set_settings(
        self,
        db: AsyncSession,
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
        assert response.json() == "OK"

        await db.refresh(user)
        assert user.language_code == "en"
        assert user.country == "USA"
