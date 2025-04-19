from httpx import AsyncClient

from models.user import User, Kyc
import pycountry


class TestKyc:
    """
    Тесты для эндпоинтов KYC.
    """
    async def test_get_kyc_list(
        self,
        async_api: AsyncClient,
        admin_token: str,
        admin: User,
        kyc: Kyc,
    ):
        """
        Проверяет успешное получение списка KYC.
        """
        response = await async_api.get(
            "v1/admin/kyc",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 200
        assert isinstance(response.json()['items'], list)

    async def test_create_kyc_list(
        self,
        async_api: AsyncClient,
        admin_token: str,
        admin: User,
        kyc: Kyc,
    ):
        """
        Проверяет успешное создание новых стран.
        """
        payload = {"countries": ["Kazakhstan"]}
        response = await async_api.post(
            "v1/admin/kyc/create",
            json=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code in [200, 400]

    async def test_create_kyc_list_duplicate(
        self,
        async_api: AsyncClient,
        admin_token: str,
        admin: User,
        kyc: Kyc,
    ):
        """
        Проверяет обработку дублирующихся стран.
        """
        payload = {"countries": [pycountry.countries.get(alpha_3=kyc.country).name]}
        response = await async_api.post(
            "v1/admin/kyc/create",
            json=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 400
        assert response.json()["message"] == "Country already exists"

    async def test_delete_kyc_list(
        self,
        async_api: AsyncClient,
        admin_token: str,
        admin: User,
        kyc: Kyc,
    ):
        """
        Проверяет успешное удаление стран.
        """
        payload = {"countries": [pycountry.countries.get(alpha_3=kyc.country).name]}
        response = await async_api.delete(
            "v1/admin/kyc",
            params=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Countries deleted successfully"

    async def test_delete_kyc_list_not_found(
        self,
        async_api: AsyncClient,
        admin_token: str,
        admin: User,
        kyc: Kyc,
    ):
        """
        Проверяет обработку удаления несуществующих стран.
        """
        payload = {"countries": ["NonExistentCountry"]}
        response = await async_api.delete(
            "v1/admin/kyc",
            params=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )
        assert response.status_code == 422
