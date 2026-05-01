from fastapi import APIRouter, Depends
from psycopg2.extensions import connection

from backend.database import get_db
from backend.schemas.analysis_schema import CorrelationResult
from backend.schemas.game_schema import DashboardSummary


router = APIRouter(tags=["analysis"])


@router.get("/analysis/correlation", response_model=list[CorrelationResult])
def get_correlation_results(db: connection = Depends(get_db)) -> list[dict]:
    query = """
        SELECT
            feature_a AS feature_x,
            feature_b AS feature_y,
            correlation AS correlation_value,
            p_value,
            sample_size
        FROM correlation_results
        ORDER BY ABS(correlation) DESC, feature_a ASC, feature_b ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: connection = Depends(get_db)) -> dict:
    query = """
        WITH sentiment_by_game AS (
            SELECT
                app_id,
                AVG((sentiment_label = 'positive')::int)::float AS positive_ratio
            FROM review_sentiments
            GROUP BY app_id
        ),
        top_genre AS (
            SELECT genre
            FROM games
            WHERE genre IS NOT NULL AND genre <> ''
            GROUP BY genre
            ORDER BY COUNT(*) DESC, genre ASC
            LIMIT 1
        )
        SELECT
            (SELECT COUNT(*)::int FROM games) AS total_games,
            (SELECT COUNT(*)::int FROM reviews) AS total_reviews,
            COALESCE((SELECT AVG(positive_ratio)::float FROM sentiment_by_game), 0) AS average_positive_ratio,
            COALESCE((SELECT genre FROM top_genre), '') AS top_genre
    """
    with db.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchone()
