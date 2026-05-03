import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from psycopg2.extras import execute_values

from db_setup_v2 import initialize_database
from db_utils import get_connection


REVIEWS_URL_TEMPLATE = "https://store.steampowered.com/appreviews/{app_id}"
logger = logging.getLogger(__name__)


def fetch_reviews_for_app(app_id, max_pages=3, page_size=100, sleep_seconds=0.5, retries=3):
    cursor_token = "*"
    collected = []

    for _ in range(max_pages):
        response = None
        for attempt in range(1, retries + 1):
            try:
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
                break
            except requests.RequestException:
                if attempt >= retries:
                    raise
                time.sleep(min(2.0, sleep_seconds * attempt))

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
    rows = [
        (
            review["steam_review_id"],
            app_id,
            review["review_text"],
            review["voted_up"],
            review["playtime_hours"],
        )
        for review in reviews
        if review.get("review_text")
    ]
    if not rows:
        return 0

    with get_connection() as conn:
        with conn.cursor() as cursor:
            execute_values(
                cursor,
                """
                INSERT INTO reviews (
                    steam_review_id,
                    app_id,
                    review_text,
                    voted_up,
                    playtime_hours,
                    language
                )
                VALUES %s
                ON CONFLICT (steam_review_id) DO UPDATE
                SET
                    review_text = EXCLUDED.review_text,
                    voted_up = EXCLUDED.voted_up,
                    playtime_hours = EXCLUDED.playtime_hours,
                    language = EXCLUDED.language,
                    collected_at = NOW()
                """,
                rows,
                template="(%s, %s, %s, %s, %s, 'english')",
                page_size=1000,
            )
        conn.commit()

    return len(rows)


def collect_reviews(app_ids=None, limit=None, max_pages=3, page_size=100, workers=8, incremental=True):
    initialize_database()

    with get_connection() as conn:
        with conn.cursor() as cursor:
            if app_ids:
                incremental_filter = ""
                if incremental:
                    incremental_filter = """
                    AND NOT EXISTS (
                        SELECT 1
                        FROM reviews r
                        WHERE r.app_id = games.app_id
                    )
                    """
                cursor.execute(
                    f"""
                    SELECT app_id, name
                    FROM games
                    WHERE app_id = ANY(%s)
                    {incremental_filter}
                    ORDER BY app_id
                    """,
                    (app_ids,),
                )
            else:
                incremental_filter = ""
                if incremental:
                    incremental_filter = """
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM reviews r
                        WHERE r.app_id = g.app_id
                    )
                    """
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
                    SELECT g.app_id, g.name
                    FROM games g
                    LEFT JOIN latest_stats ls ON ls.app_id = g.app_id
                    {incremental_filter}
                    ORDER BY
                        COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0) DESC,
                        g.app_id ASC
                """.format(incremental_filter=incremental_filter)
                params = ()
                if limit is not None:
                    query += " LIMIT %s"
                    params = (limit,)
                cursor.execute(query, params)
            games = cursor.fetchall()

    logger.info("Selected %s games for review collection.", len(games))

    def collect_one(game):
        app_id, name = game
        reviews = fetch_reviews_for_app(app_id, max_pages=max_pages, page_size=page_size)
        inserted = upsert_reviews(app_id, reviews)
        return app_id, name, inserted

    total_inserted = 0
    if workers <= 1:
        for game in games:
            try:
                app_id, name, inserted = collect_one(game)
                total_inserted += inserted
                logger.info("Collected %s reviews for %s (%s).", inserted, name, app_id)
            except Exception as exc:
                logger.warning("Failed to collect reviews for %s (%s): %s", game[1], game[0], exc)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(collect_one, game): game for game in games}
            for future in as_completed(futures):
                app_id, name = futures[future]
                try:
                    _, _, inserted = future.result()
                    total_inserted += inserted
                    logger.info("Collected %s reviews for %s (%s).", inserted, name, app_id)
                except Exception as exc:
                    logger.warning("Failed to collect reviews for %s (%s): %s", name, app_id, exc)

    logger.info("Review collection complete. Upserted %s reviews.", total_inserted)
    return total_inserted


def parse_args():
    parser = argparse.ArgumentParser(description="Collect Steam reviews into PostgreSQL.")
    parser.add_argument("--app-id", dest="app_ids", action="append", type=int, help="Specific app_id to collect.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of games queried from DB.")
    parser.add_argument("--max-pages", type=int, default=3, help="Pages per game to fetch.")
    parser.add_argument("--page-size", type=int, default=100, help="Reviews per page.")
    parser.add_argument("--workers", type=int, default=8, help="Parallel review collection workers.")
    parser.add_argument("--no-incremental", action="store_true", help="Collect games even if reviews already exist.")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    collect_reviews(
        app_ids=args.app_ids,
        limit=args.limit,
        max_pages=args.max_pages,
        page_size=args.page_size,
        workers=args.workers,
        incremental=not args.no_incremental,
    )
