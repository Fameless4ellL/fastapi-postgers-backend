from httpx import AsyncClient
from redis.asyncio import Redis

from src.models.user import User
from src.tests.test_routers.test_admin.conftest import PASSWORD


class TestAuth:
    async def test_login(
        self,
        async_api: AsyncClient,
        admin: User,
        aredis: Redis
    ):
        response = await async_api.post(
            "/v1/admin/login",
            json={
                "login": admin.username,
                "password": PASSWORD,
            }
        )

        assert response.status_code == 200
        assert "access_token" in response.json()

        token = await aredis.get(f"TOKEN:ADMINS:{admin.id}")
        assert token is not None
        assert token.decode("utf-8") == response.json()["access_token"]

    async def test_login_user_not_found(
        self,
        async_api: AsyncClient,
    ):
        response = await async_api.post(
            "/v1/admin/login",
            json={
                "login": "admin.username",
                "password": PASSWORD,
            }
        )

        data = response.json()
        assert response.status_code == 404
        assert data["message"] == "User not found"

    async def test_login_fail_password(
        self,
        async_api: AsyncClient,
        admin: User,
    ):
        response = await async_api.post(
            "/v1/admin/login",
            json={
                "login": admin.username,
                "password": "PASSWORD",
            }
        )

        data = response.json()
        assert response.status_code == 401
        assert data["message"] == "Invalid password"

    async def test_logout(
        self,
        async_api: AsyncClient,
        admin_token: str,
    ):
        """
        {
            "id": 0,
            "fullname": "string",
            "telegram": "string",
            "language_code": "string",
            "country": {
                "alpha_3": "string",
                "name": "string",
                "flag": "string"
            },
            "email": "string",
            "role": "string",
            "phone_number": "string",
            "kyc": true,
            "avatar": "string",
            "document": "string"
        }
        """
        response = await async_api.post(
            "v1/admin/logout",
            headers={"Authorization": f"Bearer {admin_token}", }
        )

        data = response.json()
        assert response.status_code == 200
        assert data == "OK"
