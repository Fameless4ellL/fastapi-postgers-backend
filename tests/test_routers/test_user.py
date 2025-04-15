from fastapi.testclient import TestClient
import pytest
from fastapi import status
from models.other import Game, Ticket
from models.user import Balance, User
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestUser:
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

    def test_get_notifications(
        self,
        api: TestClient,
        token: str,
    ):
        response = api.get(
            "/v1/notifications",
            headers={
                "Authorization": f"Bearer {token}",
            }
        )
        assert response.status_code == 200

    def test_set_settings(
        self,
        api: TestClient,
        token: str,
        user: User,
    ):
        response = api.post(
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
