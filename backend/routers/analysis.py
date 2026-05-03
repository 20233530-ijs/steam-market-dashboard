from fastapi import APIRouter, Depends, Query
from psycopg2.extensions import connection

from backend.database import get_db
from backend.schemas.analysis_schema import CorrelationResult, SentimentOverview, TopicOverview
from backend.schemas.game_schema import DashboardSummary


router = APIRouter(tags=["analysis"])
MIN_SAMPLE_SIZE = 1000


def get_reliability(sample_size: int) -> str:
    if sample_size < 1000:
        return "Low"
    if sample_size < 5000:
        return "Medium"
    return "High"


def get_warning(sample_size: int) -> str | None:
    if sample_size < MIN_SAMPLE_SIZE:
        return "데이터가 충분하지 않아 결과의 신뢰도가 낮을 수 있습니다."
    return None


@router.get("/analysis/sentiment", response_model=SentimentOverview)
def get_sentiment_overview(db: connection = Depends(get_db)) -> dict:
    query = """
        SELECT
            COUNT(*) FILTER (WHERE sentiment_label = 'positive')::int AS positive,
            COUNT(*) FILTER (WHERE sentiment_label = 'neutral')::int AS neutral,
            COUNT(*) FILTER (WHERE sentiment_label = 'negative')::int AS negative,
            COUNT(*)::int AS total
        FROM review_sentiments
    """
    with db.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone() or {}

    total = row.get("total") or 0
    positive = row.get("positive") or 0
    neutral = row.get("neutral") or 0
    negative = row.get("negative") or 0

    return {
        "positive": positive,
        "neutral": neutral,
        "negative": negative,
        "total": total,
        "positive_ratio": positive / total if total else 0.0,
        "neutral_ratio": neutral / total if total else 0.0,
        "negative_ratio": negative / total if total else 0.0,
        "min_sample_size": MIN_SAMPLE_SIZE,
        "reliability": get_reliability(total),
        "warning": get_warning(total),
    }


@router.get("/analysis/topics", response_model=list[TopicOverview])
def get_topic_overview(
    limit: int = Query(default=5, ge=1, le=50),
    db: connection = Depends(get_db),
) -> list[dict]:
    query = """
        SELECT
            topic_id,
            topic_keywords AS keywords,
            topic_weight::float AS weight,
            CASE
                WHEN SUM(topic_weight) OVER () = 0 THEN 0
                ELSE (topic_weight / SUM(topic_weight) OVER ())::float
            END AS weight_percent,
            sample_size
        FROM global_topics
        ORDER BY topic_weight DESC, topic_id ASC
        LIMIT %s
    """
    with db.cursor() as cursor:
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()

    return [
        {
            **row,
            "keywords": [keyword.strip() for keyword in row["keywords"].split(",") if keyword.strip()],
            "min_sample_size": MIN_SAMPLE_SIZE,
            "reliability": get_reliability(row["sample_size"]),
            "warning": get_warning(row["sample_size"]),
        }
        for row in rows
    ]


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
        rows = cursor.fetchall()

    return [
        {
            **row,
            "min_sample_size": MIN_SAMPLE_SIZE,
            "reliability": get_reliability(row["sample_size"]),
            "warning": get_warning(row["sample_size"]),
        }
        for row in rows
    ]


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
