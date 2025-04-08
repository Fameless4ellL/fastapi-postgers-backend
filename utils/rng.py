from typing import Optional

import requests


def get_random(min: int = 1, max: int = 90) -> Optional[int]:
    """
    Получение случайного числа
    """
    try:
        response = requests.get(
            "http://rng:8001/random",
            params={"x": min, "y": max},
            timeout=5
        )
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

    return response.json()
