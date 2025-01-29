from fastapi.testclient import TestClient
import pytest
from fastapi import status
from globals import redis
from settings import settings


@pytest.mark.skipif(
    not settings.debug,
    reason="This test is only for debug mode",
)
class TestAuth:

    @pytest.mark.parametrize(
        "user_data, expected_status, expected_response",
        [
            (
                {
                    "phone_number": "+77079898111",
                    "username": "testuser",
                    "password": "testpassword",
                    "code": "123456",
                },
                status.HTTP_400_BAD_REQUEST,
                {"message": "Invalid code"},
            ),
        ],
    )
    @pytest.mark.usefixtures("tear_down")
    def test_register(
        self,
        api: TestClient,
        user_data,
        expected_status,
        expected_response,
    ):
        response = api.post("/v1/register", json=user_data)
        assert response.status_code == expected_status
        assert response.json() == expected_response

    @pytest.mark.parametrize(
        "login_data, expected_status",
        [
            (
                {"phone_number": "+1234567890", "password": "testpassword"},
                status.HTTP_200_OK,
            ),
        ],
    )
    def test_login(self, api: TestClient, login_data, expected_status):
        response = api.post("/v1/login", json=login_data)
        assert response.status_code == expected_status
        assert "access_token" in response.json()

    @pytest.mark.parametrize(
        "token_data, expected_status",
        [
            ({"username": "testuser", "password": "testpassword"}, status.HTTP_200_OK),
        ],
    )
    def test_token(self, api: TestClient, token_data, expected_status):
        response = api.post("/v1/token", data=token_data)
        assert response.status_code == expected_status
        assert "access_token" in response.json()

    @pytest.mark.parametrize(
        "code_data, expected_status, expected_response",
        [
            (
                {"phone_number": "+77073993001"},
                status.HTTP_200_OK,
                {"message": "Code sent successfully"},
            ),
        ],
    )
    def test_send_code(
        self,
        api: TestClient,
        code_data,
        expected_status,
        expected_response,
    ):
        response = api.post("/v1/send_code", json=code_data)
        print(response.json())
        assert response.status_code == expected_status
        assert response.json()["message"] == expected_response["message"]
        assert redis.get("SMS:testclient").decode("utf-8") == str(
            response.json()["code"]
        )
