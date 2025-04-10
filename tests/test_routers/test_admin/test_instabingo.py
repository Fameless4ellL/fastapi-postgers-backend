import pytest
from httpx import AsyncClient
from fastapi import status
from models.other import InstaBingo
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestInstaBingo:
    """
    Tests for the InstaBingo endpoints.
    """
    def test_get_instabingo_default_creates_new_game_if_not_exists(
        self,
        api: AsyncClient,
        admin_token: str,
        instabingo: InstaBingo,
    ):
        response = api.get(
            "v1/admin/instabingo/default",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] is not None
        assert data["country"] is None

    def test_get_instabingo_tickets_list_returns_filtered_results(
        self,
        api: AsyncClient,
        admin_token: str,
        instabingo: InstaBingo,
    ):
        # Add test data to the database
        # (e.g., InstaBingo, Tickets, Users, etc.)
        # Ensure the data matches the filter criteria

        response = api.get(
            "v1/admin/instabingos",
            params={"countries": ["Kazakhstan"], "offset": 0, "limit": 10},
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        print(response.json())
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] > 0
        assert any(item["country"]["alpha_3"] == "KAZ" for item in data["data"])

    def test_get_instabingo_ticket_returns_400_if_not_found(
        self,
        api: AsyncClient,
        admin_token: str,
        instabingo: InstaBingo,
    ):
        response = api.get(
            "v1/admin/instabingo/9999",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json() == "Game not found"

    def test_get_generated_numbers_returns_empty_list_if_no_numbers(
        self,
        api: AsyncClient,
        admin_token: str,
        instabingo: InstaBingo,
    ):
        response = api.get(
            "v1/admin/instabingo/9999/gnumbers",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    def test_set_instabingo_as_deleted_marks_game_as_deleted(
        self,
        api: AsyncClient,
        admin_token: str,
        instabingo: InstaBingo,
    ):

        response = api.delete(
            f"v1/admin/bingo/{instabingo.id}",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == "Instabingo deleted"