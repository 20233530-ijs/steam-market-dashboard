import argparse
import sys
import time
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_DIR = PROJECT_ROOT / "database"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if str(DATABASE_DIR) not in sys.path:
    sys.path.append(str(DATABASE_DIR))

from database.db_setup_v2 import initialize_database
from database.db_utils import get_connection


STORE_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
DEFAULT_DETAILS_LIMIT = 500
MAX_RETRIES = 3


def request_appdetails(app_id, cc="us", language="english"):
    params = {
        "appids": app_id,
        "cc": cc,
        "l": language,
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(STORE_APPDETAILS_URL, params=params, timeout=20)
            response.raise_for_status()
            payload = response.json()
            app_payload = payload.get(str(app_id), {})
            if not app_payload.get("success"):
                return None
            return app_payload.get("data", {})
        except requests.RequestException as exc:
            last_error = exc
            sleep_seconds = 0.2 + (attempt * 0.1)
            print(f"Steam Store appdetails failed for {app_id} on attempt {attempt}/{MAX_RETRIES}: {exc}")
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Steam Store appdetails failed for {app_id} after {MAX_RETRIES} attempts.") from last_error


def normalize_appdetails(data):
    genres = ", ".join(genre.get("description", "") for genre in data.get("genres", []) if genre.get("description"))
    developers = ", ".join(data.get("developers", []) or [])
    publishers = ", ".join(data.get("publishers", []) or [])
    release_date = (data.get("release_date") or {}).get("date", "")
    languages = data.get("supported_languages", "")
    price_overview = data.get("price_overview") or {}
    platforms = data.get("platforms") or {}
    metacritic = data.get("metacritic") or {}
    original_price = price_overview.get("initial")
    final_price = price_overview.get("final")
    discount_percent = price_overview.get("discount_percent")
    price = final_price
    if data.get("is_free"):
        original_price = 0
        final_price = 0
        discount_percent = 0
        price = 0

    return {
        "name": data.get("name", ""),
        "genre": genres,
        "price": price,
        "is_free": bool(data.get("is_free")),
        "discount_percent": discount_percent,
        "final_price": final_price,
        "original_price": original_price,
        "release_date": release_date,
        "developer": developers,
        "publisher": publishers,
        "languages": languages,
        "header_image": data.get("header_image"),
        "capsule_image": data.get("capsule_image"),
        "website": data.get("website"),
        "is_windows": platforms.get("windows"),
        "is_mac": platforms.get("mac"),
        "is_linux": platforms.get("linux"),
        "metacritic_score": metacritic.get("score"),
    }


def fetch_target_app_ids(limit=DEFAULT_DETAILS_LIMIT):
    query = """
        WITH latest_stats AS (
            SELECT DISTINCT ON (app_id)
                app_id,
                COALESCE(positive_reviews, 0) AS positive_reviews,
                COALESCE(negative_reviews, 0) AS negative_reviews,
                collected_at
            FROM game_stats
            ORDER BY app_id, collected_at DESC, stat_id DESC
        )
        SELECT g.app_id
        FROM games g
        LEFT JOIN latest_stats ls ON ls.app_id = g.app_id
        ORDER BY
            COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0) DESC,
            g.app_id ASC
    """
    params = ()
    if limit is not None:
        query += " LIMIT %s"
        params = (limit,)

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return [row[0] for row in cursor.fetchall()]


def collect_steam_store_details(app_ids=None, limit=DEFAULT_DETAILS_LIMIT, cc="us", language="english"):
    initialize_database()
    target_app_ids = app_ids or fetch_target_app_ids(limit=limit)

    updated_count = 0
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for index, app_id in enumerate(target_app_ids, start=1):
                savepoint_created = False
                try:
                    details = request_appdetails(app_id, cc=cc, language=language)
                    if not details:
                        print(f"[{index}/{len(target_app_ids)}] No appdetails for {app_id}; skipped.")
                        continue

                    normalized = normalize_appdetails(details)
                    cursor.execute("SAVEPOINT appdetails_update")
                    savepoint_created = True
                    cursor.execute(
                        """
                        UPDATE games
                        SET
                            name = COALESCE(NULLIF(%s, ''), name),
                            genre = COALESCE(NULLIF(%s, ''), genre),
                            price = COALESCE(%s, price),
                            is_free = COALESCE(%s, is_free),
                            release_date = COALESCE(NULLIF(%s, ''), release_date),
                            developer = COALESCE(NULLIF(%s, ''), developer),
                            publisher = COALESCE(NULLIF(%s, ''), publisher),
                            languages = COALESCE(NULLIF(%s, ''), languages),
                            header_image = COALESCE(NULLIF(%s, ''), header_image),
                            capsule_image = COALESCE(NULLIF(%s, ''), capsule_image),
                            website = COALESCE(NULLIF(%s, ''), website),
                            is_windows = COALESCE(%s, is_windows),
                            is_mac = COALESCE(%s, is_mac),
                            is_linux = COALESCE(%s, is_linux),
                            metacritic_score = COALESCE(%s, metacritic_score)
                        WHERE app_id = %s
                        """,
                        (
                            normalized["name"],
                            normalized["genre"],
                            normalized["price"],
                            normalized["is_free"],
                            normalized["release_date"],
                            normalized["developer"],
                            normalized["publisher"],
                            normalized["languages"],
                            normalized["header_image"],
                            normalized["capsule_image"],
                            normalized["website"],
                            normalized["is_windows"],
                            normalized["is_mac"],
                            normalized["is_linux"],
                            normalized["metacritic_score"],
                            int(app_id),
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT INTO game_price_history (
                            app_id,
                            price,
                            discount_percent,
                            final_price
                        )
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            int(app_id),
                            normalized["original_price"],
                            normalized["discount_percent"],
                            normalized["final_price"],
                        ),
                    )
                    cursor.execute("RELEASE SAVEPOINT appdetails_update")
                    updated_count += 1
                    print(f"[{index}/{len(target_app_ids)}] Updated appdetails for {app_id}.")
                except Exception as exc:
                    if savepoint_created:
                        cursor.execute("ROLLBACK TO SAVEPOINT appdetails_update")
                    print(f"[{index}/{len(target_app_ids)}] Failed appdetails for {app_id}: {exc}")
                    continue

                time.sleep(0.3)
        conn.commit()

    print(f"Steam Store appdetails collection complete. Updated {updated_count} games.")
    return updated_count


def parse_args():
    parser = argparse.ArgumentParser(description="Enrich games with Steam Store appdetails metadata.")
    parser.add_argument("--app-id", dest="app_ids", action="append", type=int, help="Specific app_id to enrich.")
    parser.add_argument("--limit", type=int, default=DEFAULT_DETAILS_LIMIT, help="Maximum number of games to enrich.")
    parser.add_argument("--cc", default="us", help="Country code for price_overview. Default stores USD cents.")
    parser.add_argument("--language", default="english", help="Steam Store language parameter.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    collect_steam_store_details(app_ids=args.app_ids, limit=args.limit, cc=args.cc, language=args.language)
