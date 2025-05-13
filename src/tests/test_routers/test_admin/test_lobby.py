from httpx import AsyncClient


class TestSidebar:
    async def test_sidebar_global_admin(
        self,
        async_api: AsyncClient,
        admin_token: str
    ):
        """
        Test sidebar for GLOBAL_ADMIN role
        """
        response = await async_api.get(
            "/v1/admin/sidebar",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert "Dashboard" in response.json()
        assert "Admins" in response.json()
        assert "Users" in response.json()
