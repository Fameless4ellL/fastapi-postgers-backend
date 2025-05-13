from httpx import AsyncClient
from fastapi import status

from src.models import ReferralLink, User


class TestReferral:
    """
    Tests for the Referral endpoints.
    """
    async def test_deletes_referral_successfully(
        self,
        async_api: AsyncClient,
        admin_token: str,
        referral: ReferralLink,
    ):
        response = await async_api.delete(
            f"v1/admin/referrals/{referral.id}",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == "Referral deleted"

    async def test_deletes_referral_not_found(
        self,
        async_api: AsyncClient,
        admin_token: str,
        referral: ReferralLink,
    ):
        response = await async_api.delete(
            "v1/admin/referrals/999",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json() == {"message": "Referral not found"}

    async def test_gets_referral_users_successfully(
        self,
        async_api: AsyncClient,
        admin_token: str,
        referral: ReferralLink,
        referral_user: User,
    ):
        response = await async_api.get(
            f"v1/admin/referrals/{referral.id}/users?offset=0&limit=10",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["items"]) == 1
        assert response.json()["count"] == 1

    async def test_gets_referral_users_no_users(
        self,
        async_api: AsyncClient,
        admin_token: str,
        referral: ReferralLink,
    ):
        response = await async_api.get(
            f"v1/admin/referrals/{referral.id}/users?offset=0&limit=10",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["items"] == []
        assert response.json()["count"] == 0
