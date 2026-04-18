import argparse
import time

import requests

from db_setup_v2 import initialize_database
from db_utils import get_connection


REVIEWS_URL_TEMPLATE = "https://store.steampowered.com/appreviews/{app_id}"


def fetch_reviews_for_app(app_id, max_pages=3, page_size=100, sleep_seconds=0.5):
    cursor_token = "*"
    collected = []

    for _ in range(max_pages):
        response = requests.get(
            REVIEWS_URL_TEMPLATE.format(app_id=app_id),
            params={
                "json": 1,
                "language": "english",
                "filter": "recent",
                "purchase_type": "all",
                "num_per_page": page_size,
                "cursor": cursor_token,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        reviews = payload.get("reviews", [])
        if not reviews:
            break

        for review in reviews:
            collected.append(
                {
                    "steam_review_id": int(review["recommendationid"]),
                    "review_text": review.get("review", "").strip(),
                    "voted_up": bool(review.get("voted_up", False)),
                    "playtime_hours": int(review.get("author", {}).get("playtime_forever", 0) / 60),
                }
            )

        next_cursor = payload.get("cursor")
        if not next_cursor or next_cursor == cursor_token:
            break

        cursor_token = next_cursor
        time.sleep(sleep_seconds)

    return collected


def upsert_reviews(app_id, reviews):
    if not reviews:
        return 0

    inserted_count = 0
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for review in reviews:
                if not review["review_text"]:
                    continue

                cursor.execute(
                    """
                    INSERT INTO reviews (
                        steam_review_id,
                        app_id,
                        review_text,
                        voted_up,
                        playtime_hours,
                        language
                    )
                    VALUES (%s, %s, %s, %s, %s, 'english')
                    ON CONFLICT (steam_review_id) DO UPDATE
                    SET
                        review_text = EXCLUDED.review_text,
                        voted_up = EXCLUDED.voted_up,
                        playtime_hours = EXCLUDED.playtime_hours,
                        language = EXCLUDED.language,
                        collected_at = NOW()
                    """,
                    (
                        review["steam_review_id"],
                        app_id,
                        review["review_text"],
                        review["voted_up"],
                        review["playtime_hours"],
                    ),
                )
                inserted_count += 1
        conn.commit()

    return inserted_count


def collect_reviews(app_ids=None, limit=None, max_pages=3, page_size=100):
    initialize_database()

    with get_connection() as conn:
        with conn.cursor() as cursor:
            if app_ids:
                cursor.execute(
                    "SELECT app_id, name FROM games WHERE app_id = ANY(%s) ORDER BY app_id",
                    (app_ids,),
                )
            else:
                query = "SELECT app_id, name FROM games ORDER BY app_id"
                params = ()
                if limit is not None:
                    query += " LIMIT %s"
                    params = (limit,)
                cursor.execute(query, params)
            games = cursor.fetchall()

    total_inserted = 0
    for app_id, name in games:
        try:
            reviews = fetch_reviews_for_app(app_id, max_pages=max_pages, page_size=page_size)
            inserted = upsert_reviews(app_id, reviews)
            total_inserted += inserted
            print(f"Collected {inserted} reviews for {name} ({app_id}).")
        except Exception as exc:
            print(f"Failed to collect reviews for {name} ({app_id}): {exc}")
            continue

    print(f"Review collection complete. Upserted {total_inserted} reviews.")
    return total_inserted


def parse_args():
    parser = argparse.ArgumentParser(description="Collect Steam reviews into PostgreSQL.")
    parser.add_argument("--app-id", dest="app_ids", action="append", type=int, help="Specific app_id to collect.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of games queried from DB.")
    parser.add_argument("--max-pages", type=int, default=3, help="Pages per game to fetch.")
    parser.add_argument("--page-size", type=int, default=100, help="Reviews per page.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    collect_reviews(
        app_ids=args.app_ids,
        limit=args.limit,
        max_pages=args.max_pages,
        page_size=args.page_size,
    )
