from httpx import AsyncClient

from src.models.user import User, Document, Role
from src.schemes.admin import AdminRoles


class TestProfile:
    async def test_profile(
        self,
        async_api: AsyncClient,
        admin_token: str,
        admin: User,
        doc: Document,
    ):
        response = await async_api.get(
            "/v1/admin/profile",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == 200

        data = response.json()
        assert data["id"] == admin.id
        assert data["fullname"] == f"{admin.firstname} {admin.lastname}"
        assert data["telegram"] == admin.telegram
        assert data["language_code"] == admin.language_code
        assert data["email"] == admin.email
        assert data["role"] == AdminRoles[Role[admin.role].name]
        assert data["phone_number"] == admin.phone_number
        assert data["kyc"] == admin.kyc
        assert data["avatar"] is None
        assert len(data["document"]) == 1
        assert "http://localhost:8100/static/kyc/test_image.png" in data["document"][0]
