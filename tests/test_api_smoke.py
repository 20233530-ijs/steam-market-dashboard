import unittest

from backend.main import app


class ApiSmokeTests(unittest.TestCase):
    def test_health_check_route_is_registered(self):
        routes = {route.path for route in app.routes}

        self.assertIn("/", routes)
        self.assertIn("/health", routes)

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


if __name__ == "__main__":
    unittest.main()
