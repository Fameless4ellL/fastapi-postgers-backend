from typing import Optional
from httpx import AsyncClient
import requests


client = AsyncClient()


async def get_random(x: int = 1, y: int = 90) -> Optional[int]:
    """
    Получение случайного числа
    """
    try:
        response = await client.get(
            "http://rng:8001/random",
            params={"x": x, "y": y},
            timeout=5
        )
    except Exception as e:
        print(f"Error: {e}")
        return None

    return response.json()


def get_random_sync(x: int = 1, y: int = 90) -> Optional[int]:
    """
    Получение случайного числа
    """
    try:
        response = requests.get(
            "http://rng:8001/random",
            params={"x": x, "y": y},
            timeout=5
        )
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

    return response.json()
