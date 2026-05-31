from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extensions import connection

from backend.database import get_db
from backend.schemas.topic_schema import TopicResult


router = APIRouter(prefix="/games", tags=["topics"])


@router.get("/{game_id}/topics", response_model=list[TopicResult])
def get_game_topics(game_id: int, db: connection = Depends(get_db)) -> list[dict]:
    query = """
        SELECT
            topic_id,
            topic_keywords AS keywords,
            topic_weight AS weight
        FROM game_topics
        WHERE app_id = %s
        ORDER BY topic_weight DESC, topic_id ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query, (game_id,))
        topic_rows = cursor.fetchall()

    if not topic_rows:
        raise HTTPException(status_code=404, detail="Topic data not found")

    return topic_rows

