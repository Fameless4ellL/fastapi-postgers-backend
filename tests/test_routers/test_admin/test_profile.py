from fastapi.testclient import TestClient
import pycountry
import pytest
from models.user import User
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestProfile:
    def test_profile(
        self,
        api: TestClient,
        admin_token: str,
        admin: User,
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
        response = api.get(
            "/v1/admin/profile",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == 200

        response = response.json()
        assert response["id"] == admin.id
        assert response["fullname"] == f"{admin.firstname} {admin.lastname}"
        assert response["telegram"] == admin.telegram
        assert response["language_code"] == admin.language_code
        assert response["email"] == admin.email
        assert response["role"] == admin.role
        assert response["phone_number"] == admin.phone_number
        assert response["kyc"] == admin.kyc
        assert response["avatar"] is None
        assert response["document"] is None
