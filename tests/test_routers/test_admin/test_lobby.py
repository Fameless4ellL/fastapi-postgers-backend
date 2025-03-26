from fastapi.testclient import TestClient
import pytest
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestSidebar:
    def test_sidebar_global_admin(self, api: TestClient, admin_token: str):
        """
        Test sidebar for GLOBAL_ADMIN role
        """
        response = api.get(
            "/v1/admin/sidebar",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert "Dashboard" in response.json()
        assert "Admins" in response.json()
        assert "Users" in response.json()
