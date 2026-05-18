from datetime import date
import logging
from time import perf_counter, time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from psycopg2.extensions import connection

from backend.database import get_db
from backend.schemas.game_schema import (
    GameDetail,
    GameHistoryPoint,
    GameRankingItem,
    GameSearchResponse,
    GenreSummary,
    NotificationItem,
    WishlistCompareItem,
    WishlistItem,
    WishlistRequest,
    WishlistResponse,
)


router = APIRouter(prefix="/games", tags=["games"])
catalog_router = APIRouter(tags=["games"])
users_router = APIRouter(prefix="/users/me", tags=["users"])
logger = logging.getLogger(__name__)
GAME_SORT_COLUMNS = {
    "reviews": "total_reviews",
    "positive_ratio": "positive_ratio",
    "price": "price",
    "release_date": "release_date",
}
GAME_SORT_CURSOR_CASTS = {
    "reviews": "integer",
    "positive_ratio": "double precision",
    "price": "integer",
    "release_date": "text",
}
GAME_SORT_ORDERS = {"asc", "desc"}
DEFAULT_GAME_PAGE = 1
DEFAULT_GAME_LIMIT = 50
MAX_GAME_LIMIT = 100
GENRES_CACHE_TTL_SECONDS = 300
_genres_cache: dict = {"expires_at": 0.0, "data": None}


GAME_LIST_CTE = """
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
    ),
    base AS (
        SELECT
            g.app_id AS game_id,
            g.name,
            g.genre,
            g.price,
            COALESCE(g.is_free, gaf.is_free, g.price = 0) AS is_free,
            g.header_image,
            g.capsule_image,
            g.website,
            g.is_windows,
            g.is_mac,
            g.is_linux,
            g.metacritic_score,
            ls.owners,
            COALESCE(gaf.positive_review_count, ls.positive_reviews, 0) AS positive_reviews,
            COALESCE(gaf.negative_review_count, ls.negative_reviews, 0) AS negative_reviews,
            COALESCE(
                gaf.review_count,
                COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0),
                0
            ) AS total_reviews,
            CASE
                WHEN COALESCE(gaf.review_count, COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0), 0) > 0
                    THEN (
                        COALESCE(gaf.positive_review_count, ls.positive_reviews, 0)::float
                        / COALESCE(gaf.review_count, COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0), 0)
                    ) * 100
                ELSE COALESCE(gaf.sentiment_positive_ratio, 0) * 100
            END AS positive_ratio,
            COALESCE(NULLIF(ls.average_playtime, 0), rp.average_playtime) AS average_playtime,
            g.release_date,
            g.developer,
            g.publisher,
            g.languages,
            g.tags,
            ls.peak_players,
            ls.collected_at
        FROM games g
        LEFT JOIN latest_stats ls ON g.app_id = ls.app_id
        LEFT JOIN review_playtime rp ON g.app_id = rp.app_id
        LEFT JOIN game_analysis_features gaf ON g.app_id = gaf.app_id
    )
"""


def normalize_pagination(page: int, limit: int) -> tuple[int, int]:
    normalized_page = page if page >= 1 else DEFAULT_GAME_PAGE
    normalized_limit = min(max(limit, 1), MAX_GAME_LIMIT)
    return normalized_page, normalized_limit


def build_games_filter(
    search: str | None,
    genre: str | None,
    min_price: float | None,
    max_price: float | None,
    is_free: bool | None,
    min_positive_ratio: float | None,
    min_reviews: int | None,
) -> tuple[list[str], list]:
    filters = []
    params: list = []

    if search:
        filters.append(
            """(
                name ILIKE %s
                OR genre ILIKE %s
                OR tags ILIKE %s
                OR developer ILIKE %s
                OR publisher ILIKE %s
            )"""
        )
        like_search = f"%{search}%"
        params.extend([like_search] * 5)
    if genre:
        filters.append("genre ILIKE %s")
        params.append(f"%{genre}%")
    if min_price is not None:
        filters.append("price >= %s")
        params.append(min_price)
    if max_price is not None:
        filters.append("price <= %s")
        params.append(max_price)
    if is_free is not None:
        filters.append("is_free = %s")
        params.append(is_free)
    if min_positive_ratio is not None:
        filters.append("positive_ratio >= %s")
        params.append(min_positive_ratio)
    if min_reviews is not None:
        filters.append("total_reviews >= %s")
        params.append(min_reviews)

    return filters, params


def game_where_clause(filters: list[str]) -> str:
    if not filters:
        return ""
    return "WHERE " + " AND ".join(filters)


def build_filtered_games_cte(filters: list[str]) -> str:
    where_clause = game_where_clause(filters)
    return f"""
        {GAME_LIST_CTE},
        filtered AS MATERIALIZED (
            SELECT *
            FROM base
            {where_clause}
        )
    """


def build_keyset_clause(sort_column: str, sort_cast: str, order: str, has_cursor: bool) -> str:
    if not has_cursor:
        return ""
    comparator = ">" if order == "asc" else "<"
    return f"""
        WHERE {sort_column} IS NOT NULL
            AND (
                {sort_column} {comparator} %s::{sort_cast}
                OR ({sort_column} = %s::{sort_cast} AND game_id {comparator} %s)
            )
    """


def normalize_cursor_value(sort: str, cursor_value: str) -> int | float | str:
    if sort in {"reviews", "price"}:
        try:
            return int(cursor_value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid cursor_value for sort={sort}") from exc
    if sort == "positive_ratio":
        try:
            return float(cursor_value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid cursor_value for sort={sort}") from exc
    return cursor_value


def build_games_search_query(
    filters: list[str],
    sort_column: str,
    sort_cast: str,
    order: str,
    has_cursor: bool,
    include_total: bool,
    include_distribution: bool,
) -> str:
    filtered_cte = build_filtered_games_cte(filters)
    keyset_clause = build_keyset_clause(sort_column, sort_cast, order, has_cursor)
    game_id_order = order.upper()
    total_count_select = "(SELECT COUNT(*)::int FROM filtered)" if include_total else "NULL::int"
    genre_distribution_select = (
        """
            COALESCE(
                (
                    SELECT json_agg(genre_rows)
                    FROM (
                        SELECT COALESCE(NULLIF(genre, ''), 'Unknown') AS label, COUNT(*)::int AS count
                        FROM filtered
                        GROUP BY label
                        ORDER BY count DESC, label ASC
                        LIMIT 20
                    ) genre_rows
                ),
                '[]'::json
            )
        """
        if include_distribution
        else "'[]'::json"
    )
    positive_ratio_distribution_select = (
        """
            COALESCE(
                (
                    SELECT json_agg(ratio_rows)
                    FROM (
                        SELECT
                            CASE
                                WHEN positive_ratio >= 90 THEN '90-100'
                                WHEN positive_ratio >= 80 THEN '80-89'
                                WHEN positive_ratio >= 70 THEN '70-79'
                                WHEN positive_ratio >= 60 THEN '60-69'
                                WHEN positive_ratio >= 50 THEN '50-59'
                                ELSE '0-49'
                            END AS label,
                            COUNT(*)::int AS count
                        FROM filtered
                        GROUP BY label
                        ORDER BY MIN(positive_ratio) DESC
                    ) ratio_rows
                ),
                '[]'::json
            )
        """
        if include_distribution
        else "'[]'::json"
    )
    return f"""
        {filtered_cte},
        page_window AS (
            SELECT *
            FROM filtered
            {keyset_clause}
            ORDER BY {sort_column} {order.upper()} NULLS LAST, game_id {game_id_order}
            LIMIT %s
        ),
        page_window_ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (ORDER BY {sort_column} {order.upper()} NULLS LAST, game_id {game_id_order}) AS page_row_number,
                COUNT(*) OVER () AS page_count
            FROM page_window
        )
        SELECT
            COALESCE(
                (
                    SELECT json_agg(items_page)
                    FROM (
                        SELECT
                            game_id,
                            name,
                            genre,
                            price,
                            is_free,
                            header_image,
                            capsule_image,
                            website,
                            is_windows,
                            is_mac,
                            is_linux,
                            metacritic_score,
                            owners,
                            positive_reviews,
                            negative_reviews,
                            total_reviews,
                            positive_ratio,
                            average_playtime
                        FROM page_window_ranked
                        ORDER BY page_row_number ASC
                    ) items_page
                ),
                '[]'::json
            ) AS items,
            (
                SELECT json_build_object(
                    'cursor_value',
                    last_item.cursor_value,
                    'cursor_id',
                    last_item.game_id
                )
                FROM (
                    SELECT {sort_column}::text AS cursor_value, game_id
                    FROM page_window_ranked
                    WHERE {sort_column} IS NOT NULL
                        AND page_row_number = page_count
                ) last_item
                WHERE (SELECT COUNT(*) FROM page_window_ranked) = %s
            ) AS next_cursor,
            {total_count_select} AS total_count,
            {genre_distribution_select} AS genre_distribution,
            {positive_ratio_distribution_select} AS positive_ratio_distribution
    """


def ensure_user_tables(db: connection) -> None:
    with db.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_wishlist (
                user_key VARCHAR(100) NOT NULL,
                app_id INTEGER NOT NULL REFERENCES games(app_id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (user_key, app_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_notifications (
                notification_id SERIAL PRIMARY KEY,
                user_key VARCHAR(100) NOT NULL,
                app_id INTEGER REFERENCES games(app_id) ON DELETE SET NULL,
                type VARCHAR(50) NOT NULL,
                title VARCHAR(200) NOT NULL,
                message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                read_at TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS game_price_history (
                price_history_id SERIAL PRIMARY KEY,
                app_id INTEGER NOT NULL REFERENCES games(app_id) ON DELETE CASCADE,
                price INTEGER,
                discount_percent INTEGER,
                final_price INTEGER,
                collected_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
    db.commit()


def get_client_user_key(x_client_id: str | None = Header(default=None, alias="X-Client-Id")) -> str:
    client_id = (x_client_id or "").strip()
    if not client_id:
        return "anonymous"
    if len(client_id) > 100:
        raise HTTPException(status_code=400, detail="X-Client-Id must be 100 characters or fewer")
    return client_id


@router.get("", response_model=GameSearchResponse)
def get_games(
    search: str | None = Query(default=None),
    genre: str | None = Query(default=None),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    is_free: bool | None = Query(default=None),
    min_positive_ratio: float | None = Query(default=None, ge=0, le=100),
    min_reviews: int | None = Query(default=None, ge=0),
    sort: str = Query(default="reviews"),
    order: str = Query(default="desc"),
    page: int = Query(default=DEFAULT_GAME_PAGE),
    limit: int = Query(default=DEFAULT_GAME_LIMIT),
    cursor_value: str | None = Query(default=None),
    cursor_id: int | None = Query(default=None, ge=0),
    include_total: bool = Query(default=False),
    include_distribution: bool = Query(default=False),
    db: connection = Depends(get_db),
) -> dict:
    sort_column = GAME_SORT_COLUMNS.get(sort)
    if sort_column is None:
        raise HTTPException(status_code=400, detail=f"Unsupported sort: {sort}")
    sort_cast = GAME_SORT_CURSOR_CASTS[sort]
    order = order.lower()
    if order not in GAME_SORT_ORDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported order: {order}")
    if (cursor_value is None) != (cursor_id is None):
        raise HTTPException(status_code=400, detail="cursor_value and cursor_id must be provided together")

    filters, params = build_games_filter(
        search, genre, min_price, max_price, is_free, min_positive_ratio, min_reviews
    )
    page, limit = normalize_pagination(page, limit)
    has_cursor = cursor_value is not None and cursor_id is not None
    query = build_games_search_query(
        filters,
        sort_column,
        sort_cast,
        order,
        has_cursor,
        include_total,
        include_distribution,
    )
    query_params = [*params]
    if has_cursor:
        normalized_cursor_value = normalize_cursor_value(sort, cursor_value)
        query_params.extend([normalized_cursor_value, normalized_cursor_value, cursor_id])
    query_params.extend([limit, limit])

    started_at = perf_counter()
    with db.cursor() as cursor:
        cursor.execute(query, query_params)
        row = cursor.fetchone() or {}
    elapsed_ms = (perf_counter() - started_at) * 1000
    logger.info(
        "games_search_completed sort=%s order=%s page=%s limit=%s include_total=%s include_distribution=%s total_count=%s elapsed_ms=%.2f",
        sort,
        order,
        page,
        limit,
        include_total,
        include_distribution,
        row.get("total_count") or 0,
        elapsed_ms,
    )

    return {
        "items": row.get("items") or [],
        "total_count": row.get("total_count"),
        "page": page,
        "limit": limit,
        "next_cursor": row.get("next_cursor"),
        "genre_distribution": row.get("genre_distribution") or [],
        "positive_ratio_distribution": row.get("positive_ratio_distribution") or [],
    }


@catalog_router.get("/genres", response_model=list[GenreSummary])
def get_genres(db: connection = Depends(get_db)) -> list[dict]:
    now = time()
    if _genres_cache["data"] is not None and _genres_cache["expires_at"] > now:
        return _genres_cache["data"]

    query = """
        SELECT genre, COUNT(DISTINCT app_id)::int AS game_count
        FROM (
            SELECT
                g.app_id,
                trim(genre_value) AS genre
            FROM games g
            CROSS JOIN LATERAL regexp_split_to_table(COALESCE(g.genre, ''), ',') AS genre_value
        ) split_genres
        WHERE genre <> ''
        GROUP BY genre
        ORDER BY game_count DESC, genre ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    _genres_cache["data"] = rows
    _genres_cache["expires_at"] = now + GENRES_CACHE_TTL_SECONDS
    return rows


@router.get("/rankings", response_model=list[GameRankingItem])
def get_game_rankings(
    metric: str = Query(default="reviews"),
    limit: int = Query(default=10, ge=1, le=50),
    db: connection = Depends(get_db),
) -> list[dict]:
    metric_map = {
        "reviews": "total_reviews",
        "positive_ratio": "positive_ratio",
        "price": "price",
        "average_playtime": "average_playtime",
    }
    metric_column = metric_map.get(metric)
    if metric_column is None:
        raise HTTPException(status_code=400, detail=f"Unsupported metric: {metric}")

    query = f"""
        {GAME_LIST_CTE}
        SELECT
            ROW_NUMBER() OVER (ORDER BY {metric_column} DESC NULLS LAST, name ASC)::int AS rank,
            {metric_column}::float AS metric_value,
            game_id,
            name,
            genre,
            price,
            is_free,
            owners,
            positive_reviews,
            negative_reviews,
            total_reviews,
            positive_ratio,
            average_playtime
        FROM base
        ORDER BY {metric_column} DESC NULLS LAST, name ASC
        LIMIT %s
    """
    with db.cursor() as cursor:
        cursor.execute(query, (limit,))
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
            COALESCE(g.is_free, gaf.is_free, g.price = 0) AS is_free,
            g.header_image,
            g.capsule_image,
            g.website,
            g.is_windows,
            g.is_mac,
            g.is_linux,
            g.metacritic_score,
            g.release_date,
            g.developer,
            g.publisher,
            g.languages,
            g.tags,
            ls.owners,
            COALESCE(gaf.positive_review_count, ls.positive_reviews, 0) AS positive_reviews,
            COALESCE(gaf.negative_review_count, ls.negative_reviews, 0) AS negative_reviews,
            COALESCE(gaf.review_count, COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0), 0) AS total_reviews,
            CASE
                WHEN COALESCE(gaf.review_count, COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0), 0) > 0
                    THEN (
                        COALESCE(gaf.positive_review_count, ls.positive_reviews, 0)::float
                        / COALESCE(gaf.review_count, COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0), 0)
                    ) * 100
                ELSE COALESCE(gaf.sentiment_positive_ratio, 0) * 100
            END AS positive_ratio,
            COALESCE(NULLIF(ls.average_playtime, 0), rp.average_playtime) AS average_playtime,
            ls.peak_players,
            ls.collected_at
        FROM games g
        LEFT JOIN latest_stats ls ON g.app_id = ls.app_id
        LEFT JOIN review_playtime rp ON g.app_id = rp.app_id
        LEFT JOIN game_analysis_features gaf ON g.app_id = gaf.app_id
        WHERE g.app_id = %s
    """
    with db.cursor() as cursor:
        cursor.execute(query, (game_id, game_id, game_id))
        game = cursor.fetchone()

    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    return game


@router.get("/{game_id}/history", response_model=list[GameHistoryPoint])
def get_game_history(
    game_id: int,
    interval: str = Query(default="day", pattern="^(day|week|month)$"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: connection = Depends(get_db),
) -> list[dict]:
    filters = ["app_id = %s"]
    params: list = [game_id]
    if start_date:
        filters.append("collected_at::date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("collected_at::date <= %s")
        params.append(end_date)

    review_filters = " AND ".join([f"r.{item}" if item.startswith("app_id") else f"r.{item}" for item in filters])
    stats_filters = " AND ".join([f"gs.{item}" if item.startswith("app_id") else f"gs.{item}" for item in filters])
    price_filters = " AND ".join([f"ph.{item}" if item.startswith("app_id") else f"ph.{item}" for item in filters])
    query = f"""
        WITH review_history AS (
            SELECT
                date_trunc(%s, r.collected_at)::date AS period,
                COUNT(*)::int AS review_count,
                COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::int AS positive_reviews,
                COUNT(*) FILTER (WHERE rs.sentiment_label = 'negative')::int AS negative_reviews,
                CASE
                    WHEN COUNT(*) = 0 THEN 0
                    ELSE (COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::float / COUNT(*)) * 100
                END AS positive_ratio
            FROM reviews r
            LEFT JOIN review_sentiments rs ON r.review_id = rs.review_id
            WHERE {review_filters}
            GROUP BY period
        ),
        stat_history AS (
            SELECT DISTINCT ON (date_trunc(%s, gs.collected_at)::date)
                date_trunc(%s, gs.collected_at)::date AS period,
                gs.owners,
                gs.peak_players
            FROM game_stats gs
            JOIN games g ON g.app_id = gs.app_id
            WHERE {stats_filters}
            ORDER BY date_trunc(%s, gs.collected_at)::date, gs.collected_at DESC, gs.stat_id DESC
        ),
        price_history AS (
            SELECT DISTINCT ON (date_trunc(%s, ph.collected_at)::date)
                date_trunc(%s, ph.collected_at)::date AS period,
                COALESCE(ph.price, ph.final_price) AS price,
                ph.discount_percent,
                ph.final_price
            FROM game_price_history ph
            WHERE {price_filters}
            ORDER BY date_trunc(%s, ph.collected_at)::date, ph.collected_at DESC, ph.price_history_id DESC
        )
        SELECT
            COALESCE(rh.period, sh.period, ph.period) AS period,
            COALESCE(rh.review_count, 0) AS review_count,
            COALESCE(rh.positive_reviews, 0) AS positive_reviews,
            COALESCE(rh.negative_reviews, 0) AS negative_reviews,
            COALESCE(rh.positive_ratio, 0) AS positive_ratio,
            ph.price,
            ph.discount_percent,
            ph.final_price,
            sh.owners,
            sh.peak_players
        FROM review_history rh
        FULL OUTER JOIN stat_history sh ON rh.period = sh.period
        FULL OUTER JOIN price_history ph ON COALESCE(rh.period, sh.period) = ph.period
        ORDER BY period ASC
    """
    with db.cursor() as cursor:
        cursor.execute(
            query,
            (
                interval,
                *params,
                interval,
                interval,
                *params,
                interval,
                interval,
                interval,
                *params,
                interval,
            ),
        )
        rows = cursor.fetchall()

    if not rows:
        with db.cursor() as cursor:
            cursor.execute("SELECT 1 FROM games WHERE app_id = %s", (game_id,))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Game not found")
    return rows


@router.get("/{game_id}/review-trend", response_model=list[GameHistoryPoint])
def get_game_review_trend(
    game_id: int,
    interval: str = Query(default="month", pattern="^(day|week|month)$"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: connection = Depends(get_db),
) -> list[dict]:
    filters = ["r.app_id = %s"]
    params: list = [game_id]
    if start_date:
        filters.append("r.collected_at::date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("r.collected_at::date <= %s")
        params.append(end_date)

    query = f"""
        SELECT
            date_trunc(%s, r.collected_at)::date AS period,
            COUNT(*)::int AS review_count,
            COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::int AS positive_reviews,
            COUNT(*) FILTER (WHERE rs.sentiment_label = 'negative')::int AS negative_reviews,
            CASE
                WHEN COUNT(*) = 0 THEN 0
                ELSE (COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::float / COUNT(*)) * 100
            END AS positive_ratio,
            NULL::int AS price,
            NULL::int AS discount_percent,
            NULL::int AS final_price,
            NULL::varchar AS owners,
            NULL::int AS peak_players
        FROM reviews r
        LEFT JOIN review_sentiments rs ON r.review_id = rs.review_id
        WHERE {" AND ".join(filters)}
        GROUP BY period
        ORDER BY period ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query, (interval, *params))
        rows = cursor.fetchall()

    if not rows:
        with db.cursor() as cursor:
            cursor.execute("SELECT 1 FROM games WHERE app_id = %s", (game_id,))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Game not found")
    return rows


@users_router.get("/wishlist", response_model=WishlistResponse)
def get_wishlist(
    user_key: str = Depends(get_client_user_key),
    db: connection = Depends(get_db),
) -> dict:
    ensure_user_tables(db)
    query = f"""
        {GAME_LIST_CTE},
        recent_reviews AS (
            SELECT app_id, COUNT(*)::int AS review_change_30d
            FROM reviews
            WHERE collected_at >= NOW() - INTERVAL '30 days'
            GROUP BY app_id
        ),
        recent_prices AS (
            SELECT
                app_id,
                MIN(COALESCE(final_price, price))::int AS lowest_price_30d,
                MAX(COALESCE(final_price, price))::int AS highest_price_30d
            FROM game_price_history
            WHERE collected_at >= NOW() - INTERVAL '30 days'
            GROUP BY app_id
        ),
        price_edges AS (
            SELECT DISTINCT ON (app_id)
                app_id,
                FIRST_VALUE(COALESCE(final_price, price)) OVER (
                    PARTITION BY app_id
                    ORDER BY collected_at ASC, price_history_id ASC
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                ) AS first_price_30d,
                FIRST_VALUE(COALESCE(final_price, price)) OVER (
                    PARTITION BY app_id
                    ORDER BY collected_at DESC, price_history_id DESC
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                ) AS latest_price_30d
            FROM game_price_history
            WHERE collected_at >= NOW() - INTERVAL '30 days'
        )
        SELECT
            b.game_id,
            b.name,
            b.genre,
            b.price,
            b.is_free,
            b.owners,
            b.positive_reviews,
            b.negative_reviews,
            b.total_reviews,
            b.positive_ratio,
            b.average_playtime,
            CASE
                WHEN pe.first_price_30d IS NULL OR pe.latest_price_30d IS NULL THEN NULL
                ELSE (pe.latest_price_30d - pe.first_price_30d)::int
            END AS price_change_30d,
            rp.lowest_price_30d,
            rp.highest_price_30d,
            COALESCE(rr.review_change_30d, 0) AS review_change_30d
        FROM user_wishlist uw
        JOIN base b ON b.game_id = uw.app_id
        LEFT JOIN recent_reviews rr ON rr.app_id = uw.app_id
        LEFT JOIN recent_prices rp ON rp.app_id = uw.app_id
        LEFT JOIN price_edges pe ON pe.app_id = uw.app_id
        WHERE uw.user_key = %s
        ORDER BY uw.created_at DESC, b.name ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query, (user_key,))
        return {"items": cursor.fetchall()}


@users_router.post("/wishlist", response_model=WishlistResponse, status_code=status.HTTP_201_CREATED)
def add_wishlist_item(
    payload: WishlistRequest,
    user_key: str = Depends(get_client_user_key),
    db: connection = Depends(get_db),
) -> dict:
    ensure_user_tables(db)
    with db.cursor() as cursor:
        cursor.execute("SELECT 1 FROM games WHERE app_id = %s", (payload.game_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Game not found")
        cursor.execute(
            """
            INSERT INTO user_wishlist (user_key, app_id)
            VALUES (%s, %s)
            ON CONFLICT (user_key, app_id) DO NOTHING
            """,
            (user_key, payload.game_id),
        )
    db.commit()
    return get_wishlist(user_key, db)


@users_router.get("/wishlist/compare", response_model=list[WishlistCompareItem])
def compare_wishlist(
    game_ids: list[int] | None = Query(default=None),
    user_key: str = Depends(get_client_user_key),
    db: connection = Depends(get_db),
) -> list[dict]:
    ensure_user_tables(db)
    params: list = []
    game_filter = ""
    if game_ids:
        selected_ids = game_ids[:4]
        game_filter = "AND b.game_id = ANY(%s)"
        params.append(selected_ids)

    query = f"""
        {GAME_LIST_CTE}
        SELECT b.game_id, b.name, b.positive_ratio, b.total_reviews, b.price
        FROM user_wishlist uw
        JOIN base b ON b.game_id = uw.app_id
        WHERE uw.user_key = %s {game_filter}
        ORDER BY b.total_reviews DESC, b.name ASC
        LIMIT 4
    """
    with db.cursor() as cursor:
        cursor.execute(query, (user_key, *params))
        return cursor.fetchall()


@users_router.delete("/wishlist/{game_id}", response_model=WishlistResponse)
def delete_wishlist_item(
    game_id: int,
    user_key: str = Depends(get_client_user_key),
    db: connection = Depends(get_db),
) -> dict:
    ensure_user_tables(db)
    with db.cursor() as cursor:
        cursor.execute("DELETE FROM user_wishlist WHERE user_key = %s AND app_id = %s", (user_key, game_id))
    db.commit()
    return get_wishlist(user_key, db)


@users_router.get("/notifications", response_model=list[NotificationItem])
def get_notifications(
    user_key: str = Depends(get_client_user_key),
    db: connection = Depends(get_db),
) -> list[dict]:
    ensure_user_tables(db)
    query = """
        SELECT
            un.notification_id,
            un.app_id AS game_id,
            g.name AS game_name,
            un.type,
            un.title,
            un.message,
            un.created_at,
            un.read_at
        FROM user_notifications un
        LEFT JOIN games g ON g.app_id = un.app_id
        WHERE un.user_key = %s
        ORDER BY un.created_at DESC, un.notification_id DESC
    """
    with db.cursor() as cursor:
        cursor.execute(query, (user_key,))
        return cursor.fetchall()
