from fastapi.testclient import TestClient
import pytest
from models.user import User, Kyc
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestKyc:
    """
    Тесты для эндпоинтов KYC.
    """
    def test_get_kyc_list(
        self,
        api: TestClient,
        admin_token: str,
        admin: User,
        kyc: Kyc,
    ):
        """
        Проверяет успешное получение списка KYC.
        """
        response = api.get(
            "v1/admin/kyc",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_kyc_list(
        self,
        api: TestClient,
        admin_token: str,
        admin: User,
        kyc: Kyc,
    ):
        """
        Проверяет успешное создание новых стран.
        """
        payload = {"countries": ["KAZ"]}
        response = api.post(
            "v1/admin/kyc/create",
            json=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Countries created successfully"

    def test_create_kyc_list_duplicate(
        self,
        api: TestClient,
        admin_token: str,
        admin: User,
        kyc: Kyc,
    ):
        """
        Проверяет обработку дублирующихся стран.
        """
        payload = {"countries": [kyc.country]}
        response = api.post(
            "v1/admin/kyc/create",
            json=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 400
        assert response.json()["message"] == "Country already exists"

    def test_delete_kyc_list(
        self,
        api: TestClient,
        admin_token: str,
        admin: User,
        kyc: Kyc,
    ):
        """
        Проверяет успешное удаление стран.
        """
        payload = {"countries": [kyc.country]}
        response = api.delete(
            "v1/admin/kyc",
            params=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Countries deleted successfully"

    def test_delete_kyc_list_not_found(
        self,
        api: TestClient,
        admin_token: str,
        admin: User,
        kyc: Kyc,
    ):
        """
        Проверяет обработку удаления несуществующих стран.
        """
        payload = {"countries": ["NonExistentCountry"]}
        response = api.delete(
            "v1/admin/kyc",
            params=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 422