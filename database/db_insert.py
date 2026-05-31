import csv
import glob
from pathlib import Path

from db_setup_v2 import initialize_database
from db_utils import get_connection


def find_latest_csv():
    csv_files = sorted(glob.glob("steam_games_*.csv"))
    if not csv_files:
        raise FileNotFoundError("No steam_games_*.csv files were found.")
    return Path(csv_files[-1])


def insert_csv_data():
    initialize_database()
    filename = find_latest_csv()
    print(f"Importing CSV file: {filename}")

    inserted_count = 0
    with get_connection() as conn:
        with conn.cursor() as cursor:
            with open(filename, "r", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    cursor.execute(
                        """
                        INSERT INTO games (app_id, name, price)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (app_id) DO UPDATE
                        SET
                            name = EXCLUDED.name,
                            price = EXCLUDED.price
                        """,
                        (
                            int(row["app_id"]),
                            row["name"],
                            int(row.get("price", 0) or 0),
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
                            int(row["app_id"]),
                            row.get("owners", ""),
                            int(row.get("positive", 0) or 0),
                            int(row.get("negative", 0) or 0),
                            int(row.get("average_playtime", 0) or 0),
                        ),
                    )
                    inserted_count += 1
        conn.commit()

    print(f"CSV import complete. Stored {inserted_count} rows.")


if __name__ == "__main__":
    insert_csv_data()
