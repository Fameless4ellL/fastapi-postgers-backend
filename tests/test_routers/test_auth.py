import pytest
from fastapi import status
from httpx import AsyncClient
from redis.asyncio import Redis

from models.user import User


class TestAuth:
    @pytest.mark.usefixtures("tear_down")
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
        print(response.json())
        assert response.status_code == status.HTTP_200_OK

        response = await async_api.post(
            "/v1/register",
            json={
                "username": "test_user3",
                "country": "KAZ",
                "phone_number": "+77079898923",
            }
        )
        print(response.json())
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()

    async def test_login(
        self,
        async_api: AsyncClient,
        user: User,
        tear_down: None
    ):
        response = await async_api.post(
            "/v1/login",
            json={
                "username": user.username,
                "phone_number": f"+{user.phone_number}",
                "code": "123456",
            }
        )
        print(response.json())
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()

    async def test_token(
        self,
        async_api: AsyncClient,
        user: User
    ):
        response = await async_api.post(
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
    async def test_send_code(
        self,
        async_api: AsyncClient,
        aredis: Redis,
        code_data,
        expected_status,
        expected_response,
    ):
        response = await async_api.post("/v1/send_code", json=code_data)
        assert response.status_code == expected_status
        assert (await aredis.get("SMS:127.0.0.1")).decode("utf-8") == str(
            response.json()["code"]
        )

    async def test_check_code(
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
