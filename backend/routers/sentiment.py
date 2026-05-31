from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extensions import connection

from backend.database import get_db
from backend.schemas.sentiment_schema import SentimentSummary


router = APIRouter(prefix="/games", tags=["sentiment"])


@router.get("/{game_id}/sentiment", response_model=SentimentSummary)
def get_game_sentiment(game_id: int, db: connection = Depends(get_db)) -> dict:
    query = """
        SELECT
            COUNT(*) FILTER (WHERE sentiment_label = 'positive')::int AS positive_count,
            COUNT(*) FILTER (WHERE sentiment_label = 'neutral')::int AS neutral_count,
            COUNT(*) FILTER (WHERE sentiment_label = 'negative')::int AS negative_count,
            COUNT(*)::int AS total_count,
            COALESCE(AVG(compound), 0)::float AS average_compound
        FROM review_sentiments
        WHERE app_id = %s
    """
    with db.cursor() as cursor:
        cursor.execute(query, (game_id,))
        row = cursor.fetchone()

    total = row["total_count"] if row else 0
    if total == 0:
        raise HTTPException(status_code=404, detail="Sentiment data not found")

    return {
        "positive_count": row["positive_count"],
        "neutral_count": row["neutral_count"],
        "negative_count": row["negative_count"],
        "positive_ratio": row["positive_count"] / total,
        "neutral_ratio": row["neutral_count"] / total,
        "negative_ratio": row["negative_count"] / total,
        "average_compound": row["average_compound"],
    }

