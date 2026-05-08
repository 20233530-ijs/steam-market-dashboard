from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extensions import connection

from backend.database import get_db
from backend.schemas.game_schema import GameDetail, GameListItem


router = APIRouter(prefix="/games", tags=["games"])


@router.get("", response_model=list[GameListItem])
def get_games(db: connection = Depends(get_db)) -> list[dict]:
    query = """
        WITH latest_stats AS (
            SELECT DISTINCT ON (app_id)
                app_id,
                owners,
                positive_reviews,
                negative_reviews,
                average_playtime,
                peak_players,
                collected_at
            FROM game_stats
            ORDER BY app_id, collected_at DESC, stat_id DESC
        ),
        review_playtime AS (
            SELECT
                app_id,
                ROUND(AVG(playtime_hours) * 60)::int AS average_playtime
            FROM reviews
            WHERE playtime_hours IS NOT NULL AND playtime_hours > 0
            GROUP BY app_id
        )
        SELECT
            g.app_id AS game_id,
            g.name,
            g.genre,
            g.price,
            ls.owners,
            COALESCE(ls.positive_reviews, 0) AS positive_reviews,
            COALESCE(ls.negative_reviews, 0) AS negative_reviews,
            COALESCE(NULLIF(ls.average_playtime, 0), rp.average_playtime) AS average_playtime
        FROM games g
        LEFT JOIN latest_stats ls ON g.app_id = ls.app_id
        LEFT JOIN review_playtime rp ON g.app_id = rp.app_id
        ORDER BY
            (ls.app_id IS NOT NULL) DESC,
            COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0) DESC,
            g.name ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


@router.get("/{game_id}", response_model=GameDetail)
def get_game_detail(game_id: int, db: connection = Depends(get_db)) -> dict:
    query = """
        WITH latest_stats AS (
            SELECT DISTINCT ON (app_id)
                app_id,
                owners,
                positive_reviews,
                negative_reviews,
                average_playtime,
                peak_players,
                collected_at
            FROM game_stats
            WHERE app_id = %s
            ORDER BY app_id, collected_at DESC, stat_id DESC
        ),
        review_playtime AS (
            SELECT
                app_id,
                ROUND(AVG(playtime_hours) * 60)::int AS average_playtime
            FROM reviews
            WHERE app_id = %s
                AND playtime_hours IS NOT NULL
                AND playtime_hours > 0
            GROUP BY app_id
        )
        SELECT
            g.app_id AS game_id,
            g.name,
            g.genre,
            g.price,
            g.release_date,
            g.developer,
            g.publisher,
            g.languages,
            g.tags,
            ls.owners,
            COALESCE(ls.positive_reviews, 0) AS positive_reviews,
            COALESCE(ls.negative_reviews, 0) AS negative_reviews,
            COALESCE(NULLIF(ls.average_playtime, 0), rp.average_playtime) AS average_playtime,
            ls.peak_players,
            ls.collected_at
        FROM games g
        LEFT JOIN latest_stats ls ON g.app_id = ls.app_id
        LEFT JOIN review_playtime rp ON g.app_id = rp.app_id
        WHERE g.app_id = %s
    """
    with db.cursor() as cursor:
        cursor.execute(query, (game_id, game_id, game_id))
        game = cursor.fetchone()

    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    return game
