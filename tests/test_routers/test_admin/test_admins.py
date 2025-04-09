import json

from fastapi.testclient import TestClient
import pytest
from models.user import User
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestAdminPage:
    """
    Tests for the admin page endpoints.
    """
    def test_admin_list_successfully(
        self,
        api: TestClient,
        admin_token: str,
    ):
        """
        Retrieves the list of admins successfully.
        """
        response = api.get(
            "v1/admin/admins",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert "admins" in response.json()
        assert isinstance(response.json()["admins"], list)

    def test_admin_by_id_successfully(
        self,
        api: TestClient,
        admin_token: str,
        admin: User,
    ):
        """
        Retrieves a specific admin by ID successfully.
        """
        response = api.get(
            f"v1/admin/admins/{admin.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == admin.id

    def test_fails_to_retrieve_nonexistent_admin(
        self,
        api: TestClient,
        admin_token: str,
    ):
        """
        Fails to retrieve an admin that does not exist.
        """
        response = api.get(
            "v1/admin/admins/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400
        assert response.json()["message"] == "Admin not found"

    def test_creates_admin_successfully(
        self,
        api: TestClient,
        admin_token: str,
    ):
        """
        Creates a new admin successfully.
        """
        payload = {
            "item": (None,'{"username":"username","firstname":"John","lastname":"Doe","email":"john.doe@example.com","phone_number":"+77073993000","role":"Super Admin","telegram":"johndoe","country":"USA"}'),
        }
        files = {
            "avatar": ("avatar.jpg", b"fake image content", "image/jpeg"),
            "document": ("document.pdf", b"fake document content", "application/pdf"),
        }
        response = api.post(
            "v1/admin/admins/create",
            data=payload,
            files=files,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print(response.json())
        assert response.status_code == 201
        assert response.json() == "OK"

    def test_updates_admin_successfully(
        self,
        api: TestClient,
        admin_token: str,
        admin: User,
    ):
        """
        Updates an existing admin successfully.
        """
        payload = {
            "item": (None, '{"username":"username","firstname":"John","lastname":"Doe","email":"john.doe@example.com","phone_number":"+77073993000","role":"Super Admin","telegram":"johndoe","country":"USA"}'),
            "avatar": ("avatar.jpg", b"fake image content", "image/jpeg"),
            "document": ("document.pdf", b"fake document content", "application/pdf"),
        }
        response = api.put(
            f"v1/admin/admins/{admin.id}/update",
            data=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201
        assert response.json() == "OK"

    def test_fails_to_update_nonexistent_admin(
        self,
        api: TestClient,
        admin_token: str,
    ):
        """
        Fails to update an admin that does not exist.
        """
        payload = {
            "item": (None,'{"username":"username","firstname":"John","lastname":"Doe","email":"john.doe@example.com","phone_number":"+77073993000","role":"Super Admin","telegram":"johndoe","country":"USA"}'),
            "avatar": ("avatar.jpg", b"fake image content", "image/jpeg"),
            "document": ("document.pdf", b"fake document content", "application/pdf"),
        }
        response = api.put(
            "v1/admin/admins/99999/update",
            data=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        print(response.json())
        assert response.status_code == 400
        assert response.json()["message"] == "Admin not found"

    def test_deletes_admin_successfully(
        self,
        api: TestClient,
        admin_token: str,
        admin: User,
    ):
        """
        Deletes an admin successfully.
        """
        response = api.delete(
            f"v1/admin/admins/{admin.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json() == "OK"

    def test_fails_to_delete_self(
        self,
        api: TestClient,
        admin_token: str,
        admin: User,
    ):
        """
        Fails to delete the currently authenticated admin.
        """
        response = api.delete(
            f"v1/admin/admins/{admin.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400
        assert response.json()["message"] == "You can't delete yourself"
