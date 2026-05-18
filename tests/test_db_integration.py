import os
import unittest

from fastapi.testclient import TestClient

from backend.database import get_connection
from backend.main import app


APP_IDS = [-910001, -910002, -910003]


@unittest.skipUnless(os.getenv("RUN_DB_INTEGRATION") == "1", "Set RUN_DB_INTEGRATION=1 to run real DB tests.")
class RealDbGamesIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.conn = get_connection()
        with cls.conn.cursor() as cursor:
            cls.cleanup(cursor)
            cursor.execute(
                """
                INSERT INTO games (app_id, name, genre, price)
                VALUES
                    (-910001, 'Integration RPG One', 'RPG', 1000),
                    (-910002, 'Integration RPG Two', 'RPG', 2000),
                    (-910003, 'Integration Action One', 'Action', 3000)
                """
            )
            cursor.execute(
                """
                INSERT INTO game_analysis_features (
                    app_id,
                    name,
                    genre,
                    price,
                    review_count,
                    positive_review_count,
                    negative_review_count,
                    sentiment_positive_ratio,
                    is_free
                )
                VALUES
                    (-910001, 'Integration RPG One', 'RPG', 1000, 100, 90, 10, 0.90, false),
                    (-910002, 'Integration RPG Two', 'RPG', 2000, 80, 70, 10, 0.875, false),
                    (-910003, 'Integration Action One', 'Action', 3000, 60, 30, 30, 0.50, false)
                """
            )
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.conn.cursor() as cursor:
            cls.cleanup(cursor)
        cls.conn.commit()
        cls.conn.close()

    @staticmethod
    def cleanup(cursor):
        cursor.execute("DELETE FROM game_analysis_features WHERE app_id = ANY(%s)", (APP_IDS,))
        cursor.execute("DELETE FROM game_price_history WHERE app_id = ANY(%s)", (APP_IDS,))
        cursor.execute("DELETE FROM game_stats WHERE app_id = ANY(%s)", (APP_IDS,))
        cursor.execute("DELETE FROM user_wishlist WHERE app_id = ANY(%s)", (APP_IDS,))
        cursor.execute("DELETE FROM user_notifications WHERE app_id = ANY(%s)", (APP_IDS,))
        cursor.execute("DELETE FROM games WHERE app_id = ANY(%s)", (APP_IDS,))

    def test_filter_distribution_and_cursor_pagination(self):
        first_response = self.client.get(
            "/games",
            params={
                "genre": "RPG",
                "min_positive_ratio": 80,
                "sort": "reviews",
                "order": "desc",
                "limit": 1,
                "include_total": "true",
                "include_distribution": "true",
            },
        )
        self.assertEqual(first_response.status_code, 200)
        first_payload = first_response.json()
        self.assertEqual(first_payload["total_count"], 2)
        self.assertEqual(sum(item["count"] for item in first_payload["genre_distribution"]), 2)
        self.assertEqual(len(first_payload["items"]), 1)
        self.assertIsNotNone(first_payload["next_cursor"])

        next_cursor = first_payload["next_cursor"]
        second_response = self.client.get(
            "/games",
            params={
                "genre": "RPG",
                "min_positive_ratio": 80,
                "sort": "reviews",
                "order": "desc",
                "limit": 1,
                "cursor_value": next_cursor["cursor_value"],
                "cursor_id": next_cursor["cursor_id"],
            },
        )
        self.assertEqual(second_response.status_code, 200)
        second_payload = second_response.json()
        first_ids = {item["game_id"] for item in first_payload["items"]}
        second_ids = {item["game_id"] for item in second_payload["items"]}
        self.assertFalse(first_ids.intersection(second_ids))


if __name__ == "__main__":
    unittest.main()
