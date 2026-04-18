import requests

from db_setup_v2 import initialize_database
from db_utils import get_connection


STEAMSPY_URL = "https://steamspy.com/api.php?request=top100in2weeks"


def collect_all_games():
    initialize_database()
    response = requests.get(STEAMSPY_URL, timeout=20)
    response.raise_for_status()
    data = response.json()

    inserted_count = 0
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for app_id, game in data.items():
                try:
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
                except Exception as exc:
                    conn.rollback()
                    print(f"Failed to insert app {app_id}: {exc}")
                    continue
        conn.commit()

    print(f"SteamSpy collection complete. Stored {inserted_count} games.")


if __name__ == "__main__":
    collect_all_games()
