import pytest
from fastapi.testclient import TestClient
from asgi import fastapp


@pytest.fixture
def api():
    with TestClient(
        fastapp, base_url="http://api:8000",
        backend_options={"use_uvloop": True}
    ) as client:
        yield client
