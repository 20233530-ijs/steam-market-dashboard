from db_utils import get_connection


MATERIALIZED_VIEWS = [
    "mv_monthly_market_trends",
    "mv_price_review_points",
]


def refresh_materialized_views(concurrently: bool = False) -> None:
    refresh_mode = "CONCURRENTLY " if concurrently else ""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for view_name in MATERIALIZED_VIEWS:
                cursor.execute(f"REFRESH MATERIALIZED VIEW {refresh_mode}{view_name}")
                print(f"Refreshed {view_name}.")
        conn.commit()


if __name__ == "__main__":
    refresh_materialized_views()
