from fastapi.testclient import TestClient
import pytest
from fastapi import status
from globals import redis
from models.user import User
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestGames:
    @pytest.mark.usefixtures("tear_down")
    def test_register(
        self,
        api: TestClient,
        user: User,
        tear_down: None
    ):
        response = api.post(
            "/v1/check_code",
            json={
                "phone_number": user.phone_number,
                "code": "123456",
            }
        )
        assert response.status_code == status.HTTP_200_OK

        response = api.post(
            "/v1/register",
            json={
                "username": "testuser",
                "country": "KAZ",
                "phone_number": "+77073993001",
            }
        )
        print(response.json())
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()
