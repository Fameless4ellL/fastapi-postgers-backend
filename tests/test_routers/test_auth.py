from fastapi.testclient import TestClient
import pytest
from fastapi import status
from httpx import AsyncClient

from globals import redis
from models.user import User
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestAuth:
    @pytest.mark.usefixtures("tear_down")
    @pytest.mark.asyncio
    async def test_register(
        self,
        async_api: AsyncClient,
        user: User,
        tear_down: None
    ):
        response = await async_api.post(
            "/v1/check_code",
            json={
                "phone_number": user.phone_number,
                "code": "123456",
            }
        )
        assert response.status_code == status.HTTP_200_OK

        response = await async_api.post(
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

    def test_login(
        self,
        api: TestClient,
        user: User,
        tear_down: None
    ):
        response = api.post(
            "/v1/login",
            json={
                "username": user.username,
                "phone_number": user.phone_number,
                "code": "123456",
            }
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()

    def test_token(
        self,
        api: TestClient,
        user: User
    ):
        response = api.post(
            "/v1/token",
            # send form data
            data={
                "username": user.username,
                "password": "test_password",
                "grant_type": "password",
                "scope": "read write",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()

    @pytest.mark.parametrize(
        "code_data, expected_status, expected_response",
        [
            (
                {"phone_number": "+77073993001"},
                status.HTTP_200_OK,
                {"message": "Code sent successfully"},
            ),
        ],
    )
    def test_send_code(
        self,
        api: TestClient,
        code_data,
        expected_status,
        expected_response,
    ):
        response = api.post("/v1/send_code", json=code_data)
        assert response.status_code == expected_status
        assert redis.get("SMS:testclient").decode("utf-8") == str(
            response.json()["code"]
        )

    def test_check_code(
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
