from fastapi.testclient import TestClient
import pytest
from fastapi import status
from models.user import Balance
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestApp:
    def test_balance(
        self,
        api: TestClient,
        token: str,
        balance: Balance,
    ):
        response = api.get(
            "/v1/profile",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["balance"] == 0
        assert response.json()["locale"] == "EN"

    def test_deposit(
        self,
        api: TestClient,
        token: str,
        balance: Balance,
    ):
        response = api.post(
            "/v1/deposit",
            json={"amount": 100},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK

    def test_withdraw(
        self,
        api: TestClient,
        token: str,
        balance: Balance,
    ):
        response = api.post(
            "/v1/withdraw",
            json={"amount": 100},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK

    def test_tickets(
        self,
        api: TestClient,
        token: str,
    ):
        response = api.get(
            "/v1/tickets",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"tickets": [], "count": 0}
