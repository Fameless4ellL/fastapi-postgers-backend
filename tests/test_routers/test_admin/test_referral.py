import pytest
from httpx import AsyncClient
from fastapi import status

from models import ReferralLink, User
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestReferral:
    """
    Tests for the Referral endpoints.
    """
    def test_deletes_referral_successfully(
        self,
        api: AsyncClient,
        admin_token: str,
        referral: ReferralLink,
    ):
        response = api.delete(
            f"v1/admin/referrals/{referral.id}",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == "Referral deleted"

    def test_deletes_referral_not_found(
        self,
        api: AsyncClient,
        admin_token: str,
        referral: ReferralLink,
    ):
        response = api.delete(
            "v1/admin/referrals/999",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json() == {"message": "Referral not found"}

    def test_gets_referral_users_successfully(
        self,
        api: AsyncClient,
        admin_token: str,
        referral: ReferralLink,
        referral_user: User,
    ):
        response = api.get(
            f"v1/admin/referrals/{referral.id}/users?offset=0&limit=10",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["items"] == []
        assert response.json()["count"] == 0

    def test_gets_referral_users_no_users(
        self,
        api: AsyncClient,
        admin_token: str,
        referral: ReferralLink,
    ):
        response = api.get(
            f"v1/admin/referrals/{referral.id}/users?offset=0&limit=10",
            headers={
                "Authorization": f"Bearer {admin_token}",
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["items"] == []
        assert response.json()["count"] == 0
