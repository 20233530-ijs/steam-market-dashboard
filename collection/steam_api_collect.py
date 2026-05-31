import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_DIR = PROJECT_ROOT / "database"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if str(DATABASE_DIR) not in sys.path:
    sys.path.append(str(DATABASE_DIR))

from database.db_setup_v2 import initialize_database
from database.db_utils import get_connection


STEAM_WEB_API_APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
DEFAULT_STEAM_WEB_API_LIMIT = 1000
DEFAULT_MAX_RESULTS = 1000
MAX_RETRIES = 3


def get_api_key():
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("API_KEY is missing from .env.")
    return api_key


def request_app_list_page(api_key, max_results=DEFAULT_MAX_RESULTS, last_appid=None):
    params = {
        "key": api_key,
        "include_games": 1,
        "max_results": max_results,
    }
    if last_appid is not None:
        params["last_appid"] = last_appid

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(STEAM_WEB_API_APP_LIST_URL, params=params, timeout=30)
            response.raise_for_status()
            return response.json().get("response", {})
        except requests.RequestException as exc:
            last_error = exc
            sleep_seconds = 0.2 + (attempt * 0.1)
            print(f"Steam Web API request failed on attempt {attempt}/{MAX_RETRIES}: {exc}")
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Steam Web API request failed after {MAX_RETRIES} attempts.") from last_error


def fetch_steam_web_api_apps(game_limit=DEFAULT_STEAM_WEB_API_LIMIT, max_results=DEFAULT_MAX_RESULTS):
    api_key = get_api_key()
    apps = []
    seen_app_ids = set()
    last_appid = None

    while True:
        payload = request_app_list_page(api_key, max_results=max_results, last_appid=last_appid)
        page_apps = payload.get("apps", [])
        if not page_apps:
            break

        for app in page_apps:
            app_id = app.get("appid")
            if app_id in seen_app_ids:
                continue
            seen_app_ids.add(app_id)
            apps.append(app)
            if game_limit is not None and len(apps) >= game_limit:
                return apps

        next_last_appid = payload.get("last_appid") or page_apps[-1].get("appid")
        if not payload.get("have_more_results") or next_last_appid == last_appid:
            break

        last_appid = next_last_appid
        time.sleep(0.3)

    return apps


def collect_steam_web_api_games(max_results=100, game_limit=None):
    initialize_database()
    apps = fetch_steam_web_api_apps(game_limit=game_limit, max_results=max_results)

    stored_count = 0
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for app in apps:
                app_id = app.get("appid")
                name = app.get("name")
                if not app_id or not name:
                    continue

                cursor.execute(
                    """
                    INSERT INTO games (app_id, name)
                    VALUES (%s, %s)
                    ON CONFLICT (app_id) DO UPDATE
                    SET name = COALESCE(NULLIF(games.name, ''), EXCLUDED.name)
                    """,
                    (int(app_id), name),
                )
                stored_count += 1
        conn.commit()

    print(f"Steam Web API collection complete. Stored {stored_count} app ids/names.")
    return stored_count


def parse_args():
    parser = argparse.ArgumentParser(description="Collect app ids and names from Steam Web API.")
    parser.add_argument(
        "--game-limit",
        type=int,
        default=DEFAULT_STEAM_WEB_API_LIMIT,
        help="Maximum number of Steam Web API games to store.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        help="Steam Web API page size passed as max_results.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    collect_steam_web_api_games(game_limit=args.game_limit, max_results=args.max_results)


if __name__ == "__main__":
    main()
