import argparse

import requests

from db_setup_v2 import initialize_database
from db_utils import get_connection


STEAMSPY_URL = "https://steamspy.com/api.php"
DEFAULT_STEAMSPY_REQUEST = "all"
DEFAULT_GAME_LIMIT = 500


def fetch_steamspy_games(request_name=DEFAULT_STEAMSPY_REQUEST, limit=DEFAULT_GAME_LIMIT):
    response = requests.get(
        STEAMSPY_URL,
        params={"request": request_name},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()

    games = list(data.items())
    games.sort(
        key=lambda item: (
            int(item[1].get("positive", 0) or 0) + int(item[1].get("negative", 0) or 0),
            int(item[1].get("positive", 0) or 0),
        ),
        reverse=True,
    )

    if limit is not None:
        games = games[:limit]

    return games


def collect_all_games(limit=DEFAULT_GAME_LIMIT, request_name=DEFAULT_STEAMSPY_REQUEST):
    initialize_database()
    games = fetch_steamspy_games(request_name=request_name, limit=limit)

    inserted_count = 0
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for app_id, game in games:
                try:
                    cursor.execute("SAVEPOINT game_insert")
                    cursor.execute(
                        """
                        INSERT INTO games (app_id, name, genre, price, tags)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (app_id) DO UPDATE
                        SET
                            name = EXCLUDED.name,
                            genre = EXCLUDED.genre,
                            price = EXCLUDED.price,
                            tags = EXCLUDED.tags
                        """,
                        (
                            int(app_id),
                            game["name"],
                            game.get("genre", ""),
                            game.get("price", 0),
                            str(game.get("tags", "")),
                        ),
                    )

                    cursor.execute(
                        """
                        INSERT INTO game_stats (
                            app_id,
                            owners,
                            positive_reviews,
                            negative_reviews,
                            average_playtime
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            int(app_id),
                            game.get("owners", ""),
                            game.get("positive", 0),
                            game.get("negative", 0),
                            game.get("average_forever", 0),
                        ),
                    )
                    inserted_count += 1
                    cursor.execute("RELEASE SAVEPOINT game_insert")
                except Exception as exc:
                    cursor.execute("ROLLBACK TO SAVEPOINT game_insert")
                    print(f"Failed to insert app {app_id}: {exc}")
                    continue
        conn.commit()

    print(
        f"SteamSpy collection complete. Stored {inserted_count} games "
        f"from request={request_name}, limit={limit}."
    )
    return inserted_count


def parse_args():
    parser = argparse.ArgumentParser(description="Collect SteamSpy game metadata and latest stats.")
    parser.add_argument(
        "--request",
        dest="request_name",
        default=DEFAULT_STEAMSPY_REQUEST,
        help="SteamSpy request name. Use 'all' for a larger dataset or 'top100in2weeks' for a small sample.",
    )
    parser.add_argument(
        "--game-limit",
        type=int,
        default=DEFAULT_GAME_LIMIT,
        help="Maximum number of games to store. Use 1000+ for stronger game-level correlation analysis.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    collect_all_games(limit=args.game_limit, request_name=args.request_name)
