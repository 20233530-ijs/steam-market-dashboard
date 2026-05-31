import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.database import get_db
from backend.main import DEFAULT_CORS_ORIGINS, app, get_allowed_origins
from backend.routers.games import (
    build_games_filter,
    build_games_search_query,
    build_keyset_clause,
    normalize_cursor_value,
    normalize_pagination,
)


class FakeCursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, row=None, rows=None):
        self.cursor_obj = FakeCursor(row=row, rows=rows)

    def cursor(self):
        return self.cursor_obj


class ApiSmokeTests(unittest.TestCase):
    def test_health_check_route_is_registered(self):
        routes = {route.path for route in app.routes}

        self.assertIn("/", routes)
        self.assertIn("/health", routes)

    def test_cors_origins_use_env_when_configured(self):
        with patch.dict("os.environ", {"BACKEND_CORS_ORIGINS": "https://frontend.example.com"}, clear=False):
            self.assertEqual(get_allowed_origins(), ["https://frontend.example.com"])

    def test_cors_origins_fall_back_to_local_development_defaults(self):
        with patch.dict("os.environ", {"BACKEND_CORS_ORIGINS": ""}, clear=False):
            self.assertEqual(get_allowed_origins(), DEFAULT_CORS_ORIGINS)

    def test_correlation_route_has_response_model_fields(self):
        schema = app.openapi()
        response_schema = schema["paths"]["/analysis/correlation"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        item_ref = response_schema["items"]["$ref"]
        schema_name = item_ref.rsplit("/", 1)[-1]
        properties = schema["components"]["schemas"][schema_name]["properties"]

        self.assertTrue(
            {"feature_x", "feature_y", "correlation_value", "p_value", "sample_size"}.issubset(properties)
        )

    def test_analysis_overview_routes_are_registered(self):
        routes = {route.path for route in app.routes}

        self.assertIn("/analysis/sentiment", routes)
        self.assertIn("/analysis/topics", routes)

    def test_frontend_data_routes_are_registered(self):
        routes = {route.path for route in app.routes}

        expected_routes = {
            "/games",
            "/genres",
            "/games/rankings",
            "/games/{game_id}/history",
            "/games/{game_id}/review-trend",
            "/games/{game_id}/reviews/insights",
            "/analysis/genre-stats",
            "/analysis/price-band-stats",
            "/analysis/platform-stats",
            "/analysis/genre-trends",
            "/analysis/price-trends",
            "/analysis/topics/sentiment",
            "/analysis/topics/by-genre",
            "/analysis/release-year-stats",
            "/analysis/trends",
            "/analysis/price-review",
            "/analysis/topics/clusters",
            "/users/me/wishlist",
            "/users/me/wishlist/compare",
            "/users/me/notifications",
        }

        self.assertTrue(expected_routes.issubset(routes))

    def test_games_response_schema_includes_frontend_metadata_fields(self):
        schema = app.openapi()
        properties = schema["components"]["schemas"]["GameListItem"]["properties"]

        self.assertTrue(
            {
                "header_image",
                "capsule_image",
                "website",
                "is_windows",
                "is_mac",
                "is_linux",
                "metacritic_score",
            }.issubset(properties)
        )

    def test_analysis_aggregate_routes_return_200_with_fake_db(self):
        fake_db = FakeConnection(rows=[])

        def override_db():
            yield fake_db

        app.dependency_overrides[get_db] = override_db
        try:
            client = TestClient(app)
            for path in (
                "/analysis/genre-stats",
                "/analysis/price-band-stats",
                "/analysis/platform-stats",
                "/analysis/genre-trends",
                "/analysis/price-trends",
                "/analysis/release-year-stats",
            ):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"items": []})
        finally:
            app.dependency_overrides.clear()

    def test_topic_fallback_routes_return_200_with_fake_db(self):
        fake_db = FakeConnection(rows=[])

        def override_db():
            yield fake_db

        app.dependency_overrides[get_db] = override_db
        try:
            client = TestClient(app)
            topic_sentiment = client.get("/analysis/topics/sentiment")
            topics_by_genre = client.get("/analysis/topics/by-genre")
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(topic_sentiment.status_code, 200)
        self.assertFalse(topic_sentiment.json()["topic_sentiment_available"])
        self.assertEqual(topic_sentiment.json()["items"], [])
        self.assertEqual(topics_by_genre.status_code, 200)
        self.assertFalse(topics_by_genre.json()["topic_sentiment_available"])
        self.assertEqual(topics_by_genre.json()["items"], [])

    def test_wishlist_schema_includes_recent_price_metrics(self):
        schema = app.openapi()
        properties = schema["components"]["schemas"]["WishlistItem"]["properties"]

        self.assertTrue({"price_change_30d", "lowest_price_30d", "highest_price_30d"}.issubset(properties))

    def test_wishlist_routes_keep_x_client_id_header_contract(self):
        schema = app.openapi()

        operations = [
            ("/users/me/wishlist", "get"),
            ("/users/me/wishlist", "post"),
            ("/users/me/wishlist/compare", "get"),
            ("/users/me/wishlist/{game_id}", "delete"),
            ("/users/me/notifications", "get"),
        ]

        for path, method in operations:
            parameters = schema["paths"][path][method]["parameters"]
            self.assertTrue(any(parameter["name"] == "X-Client-Id" and parameter["in"] == "header" for parameter in parameters))

    def test_auth_routes_are_not_registered(self):
        routes = {route.path for route in app.routes}

        self.assertFalse(any(route.startswith("/auth") for route in routes))

    def test_games_query_uses_single_filtered_dataset_for_distributions(self):
        filters, _ = build_games_filter("portal", "Action", 0, 3000, False, 70, 100)
        query = build_games_search_query(filters, "total_reviews", "integer", "desc", False, True, True)

        self.assertIn("filtered AS MATERIALIZED", query)
        self.assertIn("page_window AS", query)
        self.assertNotIn("OFFSET", query)
        self.assertEqual(query.count("FROM filtered"), 4)
        self.assertEqual(query.count("name ILIKE %s"), 1)
        self.assertEqual(query.count("genre ILIKE %s"), 2)
        self.assertEqual(query.count("positive_ratio >= %s"), 1)
        self.assertEqual(query.count("total_reviews >= %s"), 1)

    def test_games_query_skips_count_and_distribution_by_default(self):
        filters, _ = build_games_filter(None, None, None, None, None, None, None)
        query = build_games_search_query(filters, "total_reviews", "integer", "desc", False, False, False)

        self.assertIn("NULL::int AS total_count", query)
        self.assertIn("'[]'::json AS genre_distribution", query)
        self.assertIn("'[]'::json AS positive_ratio_distribution", query)
        self.assertNotIn("SELECT COUNT(*)::int FROM filtered", query)
        self.assertNotIn("GROUP BY label", query)

    def test_games_endpoint_pagination_and_empty_response_are_normalized(self):
        fake_row = {
            "items": [],
            "total_count": None,
            "next_cursor": None,
            "genre_distribution": [],
            "positive_ratio_distribution": [],
        }
        fake_db = FakeConnection(fake_row)

        def override_db():
            yield fake_db

        app.dependency_overrides[get_db] = override_db
        try:
            response = TestClient(app).get("/games?page=0&limit=500&search=not-found")
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"], [])
        self.assertIsNone(payload["total_count"])
        self.assertEqual(payload["genre_distribution"], [])
        self.assertEqual(payload["positive_ratio_distribution"], [])
        self.assertIsNone(payload["next_cursor"])
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["limit"], 100)
        self.assertEqual(fake_db.cursor_obj.executed[0][1][-2:], [100, 100])

    def test_games_endpoint_includes_total_and_distribution_when_requested(self):
        fake_row = {
            "items": [],
            "total_count": 2,
            "next_cursor": None,
            "genre_distribution": [{"label": "RPG", "count": 2}],
            "positive_ratio_distribution": [{"label": "80-89", "count": 2}],
        }
        fake_db = FakeConnection(fake_row)

        def override_db():
            yield fake_db

        app.dependency_overrides[get_db] = override_db
        try:
            response = TestClient(app).get("/games?include_total=true&include_distribution=true")
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        query, _ = fake_db.cursor_obj.executed[0]
        self.assertEqual(payload["total_count"], 2)
        self.assertEqual(payload["genre_distribution"], [{"label": "RPG", "count": 2}])
        self.assertEqual(payload["positive_ratio_distribution"], [{"label": "80-89", "count": 2}])
        self.assertIn("SELECT COUNT(*)::int FROM filtered", query)
        self.assertIn("GROUP BY label", query)

    def test_games_endpoint_sorting_uses_whitelisted_columns(self):
        fake_row = {
            "items": [
                {
                    "game_id": 1,
                    "name": "A",
                    "genre": "Action",
                    "price": 1000,
                    "is_free": False,
                    "owners": None,
                    "positive_reviews": 9,
                    "negative_reviews": 1,
                    "total_reviews": 10,
                    "positive_ratio": 90.0,
                    "average_playtime": None,
                }
            ],
            "total_count": 1,
            "next_cursor": {"cursor_value": "90.0", "cursor_id": 1},
            "genre_distribution": [{"label": "Action", "count": 1}],
            "positive_ratio_distribution": [{"label": "90-100", "count": 1}],
        }
        fake_db = FakeConnection(fake_row)

        def override_db():
            yield fake_db

        app.dependency_overrides[get_db] = override_db
        try:
            response = TestClient(app).get("/games?sort=positive_ratio&order=asc&page=2&limit=10")
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        query, params = fake_db.cursor_obj.executed[0]
        self.assertIn("ORDER BY positive_ratio ASC NULLS LAST, game_id ASC", query)
        self.assertEqual(params[-2:], [10, 10])
        self.assertEqual(response.json()["next_cursor"], {"cursor_value": "90.0", "cursor_id": 1})

    def test_games_endpoint_uses_keyset_cursor_when_provided(self):
        fake_row = {
            "items": [],
            "total_count": None,
            "next_cursor": None,
            "genre_distribution": [],
            "positive_ratio_distribution": [],
        }
        fake_db = FakeConnection(fake_row)

        def override_db():
            yield fake_db

        app.dependency_overrides[get_db] = override_db
        try:
            response = TestClient(app).get(
                "/games?sort=reviews&order=desc&cursor_value=500&cursor_id=42&limit=25"
            )
        finally:
            app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        query, params = fake_db.cursor_obj.executed[0]
        self.assertIn("total_reviews < %s::integer", query)
        self.assertIn("game_id < %s", query)
        self.assertNotIn("OFFSET %s", query)
        self.assertEqual(params, [500, 500, 42, 25, 25])

    def test_games_endpoint_requires_complete_cursor(self):
        response = TestClient(app).get("/games?cursor_value=500")

        self.assertEqual(response.status_code, 400)

    def test_games_endpoint_rejects_invalid_numeric_cursor(self):
        response = TestClient(app).get("/games?sort=reviews&cursor_value=abc&cursor_id=1")

        self.assertEqual(response.status_code, 400)

    def test_games_endpoint_rejects_unsafe_sorting(self):
        response = TestClient(app).get("/games?sort=price;DROP TABLE games")

        self.assertEqual(response.status_code, 400)

    def test_normalize_pagination_caps_limit(self):
        self.assertEqual(normalize_pagination(-3, 500), (1, 100))
        self.assertEqual(normalize_pagination(3, 0), (3, 1))

    def test_normalize_cursor_value_matches_sort_type(self):
        self.assertEqual(normalize_cursor_value("reviews", "42"), 42)
        self.assertEqual(normalize_cursor_value("positive_ratio", "87.5"), 87.5)
        self.assertEqual(normalize_cursor_value("release_date", "2024-01-01"), "2024-01-01")

    def test_keyset_clause_direction_changes_with_sort_order(self):
        desc_clause = build_keyset_clause("total_reviews", "integer", "desc", True)
        asc_clause = build_keyset_clause("price", "integer", "asc", True)

        self.assertIn("total_reviews < %s::integer", desc_clause)
        self.assertIn("game_id < %s", desc_clause)
        self.assertIn("price > %s::integer", asc_clause)
        self.assertIn("game_id > %s", asc_clause)


if __name__ == "__main__":
    unittest.main()
