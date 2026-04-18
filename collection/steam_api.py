import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


def main():
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("API_KEY is missing from .env.")

    response = requests.get(
        "https://api.steampowered.com/IStoreService/GetAppList/v1/",
        params={"key": api_key, "include_games": 1, "limit": 10},
        timeout=20,
    )
    response.raise_for_status()
    apps = response.json()["response"]["apps"]

    print(f"Steam API connection successful. Retrieved {len(apps)} games.")
    for app in apps[:5]:
        print(f"{app['appid']} - {app['name']}")


if __name__ == "__main__":
    main()
