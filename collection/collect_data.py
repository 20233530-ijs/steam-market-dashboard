import csv
from datetime import datetime

import requests


STEAMSPY_URL = "https://steamspy.com/api.php?request=top100in2weeks"


def export_top_games_csv():
    print("Collecting SteamSpy top games data...")
    response = requests.get(STEAMSPY_URL, timeout=20)
    response.raise_for_status()
    data = response.json()

    filename = f"steam_games_{datetime.now().strftime('%Y%m%d')}.csv"
    with open(filename, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["app_id", "name", "owners", "positive", "negative", "average_playtime", "price"])

        for app_id, game in data.items():
            writer.writerow(
                [
                    app_id,
                    game["name"],
                    game["owners"],
                    game["positive"],
                    game["negative"],
                    game["average_forever"],
                    game["price"],
                ]
            )

    print(f"Saved {len(data)} games to {filename}.")


if __name__ == "__main__":
    export_top_games_csv()
