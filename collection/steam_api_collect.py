import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from database.db_setup_v2 import initialize_database
from database.db_utils import get_connection


def main():
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("API_KEY is missing from .env.")

    print("Collecting game list from Steam Web API...")
    response = requests.get(
        "https://api.steampowered.com/IStoreService/GetAppList/v1/",
        params={"key": api_key, "include_games": 1, "limit": 100},
        timeout=20,
    )
    response.raise_for_status()
    apps = response.json()["response"]["apps"]
    print(f"Fetched {len(apps)} games.")

    initialize_database()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for app in apps:
                cursor.execute(
                    """
                    INSERT INTO games (app_id, name)
                    VALUES (%s, %s)
                    ON CONFLICT (app_id) DO UPDATE
                    SET name = EXCLUDED.name
                    """,
                    (app["appid"], app["name"]),
                )
        conn.commit()

    print(f"Stored {len(apps)} games in the database.")


if __name__ == "__main__":
    main()
