from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from psycopg2.extensions import connection

from backend.database import get_db
from backend.schemas.analysis_schema import (
    AnalysisTrendsResponse,
    CorrelationResult,
    GenreStatsResponse,
    PriceReviewPoint,
    PriceBandStatsResponse,
    PriceTrendsResponse,
    PlatformStatsResponse,
    GenreTopicsResponse,
    GenreTrendsResponse,
    ReleaseYearStatsResponse,
    ReviewInsightsResponse,
    SentimentOverview,
    TopicSentimentResponse,
    TopicClusterResponse,
    TopicOverview,
)
from backend.schemas.game_schema import DashboardSummary


router = APIRouter(tags=["analysis"])
MIN_SAMPLE_SIZE = 1000
TOPIC_CATEGORY_VALUES = """
    VALUES
        ('gameplay', ARRAY['gameplay', 'combat', 'mechanic', 'controls', 'fun']),
        ('bugs', ARRAY['bug', 'crash', 'glitch', 'broken', 'error']),
        ('graphics', ARRAY['graphics', 'visual', 'art', 'animation', 'beautiful']),
        ('performance', ARRAY['performance', 'fps', 'lag', 'optimization', 'stutter']),
        ('story', ARRAY['story', 'character', 'narrative', 'dialogue', 'ending']),
        ('price', ARRAY['price', 'value', 'worth', 'expensive', 'cheap']),
        ('multiplayer', ARRAY['multiplayer', 'coop', 'online', 'server', 'matchmaking'])
"""


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


def get_summary_metrics(db: connection, start_date: date | None, end_date: date | None) -> dict:
    review_filters = []
    params = []
    if start_date:
        review_filters.append("r.collected_at::date >= %s")
        params.append(start_date)
    if end_date:
        review_filters.append("r.collected_at::date <= %s")
        params.append(end_date)
    review_where = "WHERE " + " AND ".join(review_filters) if review_filters else ""

    query = """
        WITH filtered_reviews AS (
            SELECT r.review_id, r.app_id
            FROM reviews r
            {review_where}
        ),
        sentiment_by_game AS (
            SELECT
                fr.app_id,
                AVG((sentiment_label = 'positive')::int)::float AS positive_ratio
            FROM filtered_reviews fr
            JOIN review_sentiments rs ON fr.review_id = rs.review_id
            GROUP BY fr.app_id
        ),
        top_genre AS (
            SELECT g.genre
            FROM filtered_reviews fr
            JOIN games g ON g.app_id = fr.app_id
            WHERE g.genre IS NOT NULL AND g.genre <> ''
            GROUP BY g.genre
            ORDER BY COUNT(*) DESC, g.genre ASC
            LIMIT 1
        )
        SELECT
            (SELECT COUNT(*)::int FROM games) AS total_games,
            (SELECT COUNT(*)::int FROM filtered_reviews) AS total_reviews,
            COALESCE((SELECT AVG(positive_ratio)::float FROM sentiment_by_game), 0) AS average_positive_ratio,
            COALESCE((SELECT genre FROM top_genre), '') AS top_genre
    """.format(review_where=review_where)
    with db.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchone()


def percent_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return ((current - previous) / previous) * 100


def date_filters(alias: str, start_date: date | None, end_date: date | None) -> tuple[list[str], list]:
    filters = []
    params: list = []
    if start_date:
        filters.append(f"{alias}.collected_at::date >= %s")
        params.append(start_date)
    if end_date:
        filters.append(f"{alias}.collected_at::date <= %s")
        params.append(end_date)
    return filters, params


def where_clause(filters: list[str]) -> str:
    return "WHERE " + " AND ".join(filters) if filters else ""


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: connection = Depends(get_db),
) -> dict:
    current = get_summary_metrics(db, start_date, end_date)
    if not start_date or not end_date:
        return {
            **current,
            "average_positive_ratio": current["average_positive_ratio"] * 100,
            "period": None,
            "previous_period": None,
            "changes": None,
        }

    period_days = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    previous = get_summary_metrics(db, previous_start, previous_end)

    current_ratio = current["average_positive_ratio"] * 100
    previous_ratio = previous["average_positive_ratio"] * 100

    return {
        **current,
        "average_positive_ratio": current_ratio,
        "period": {"start_date": start_date, "end_date": end_date},
        "previous_period": {"start_date": previous_start, "end_date": previous_end},
        "changes": {
            "total_reviews_percent": percent_change(current["total_reviews"], previous["total_reviews"]),
            "average_positive_ratio_points": current_ratio - previous_ratio,
            "total_games_percent": percent_change(current["total_games"], previous["total_games"]),
        },
    }


@router.get("/analysis/trends", response_model=AnalysisTrendsResponse)
def get_analysis_trends(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    top_genres_limit: int = Query(default=5, ge=1, le=10),
    db: connection = Depends(get_db),
) -> dict:
    filters = []
    params: list = []
    if start_date:
        filters.append("r.collected_at::date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("r.collected_at::date <= %s")
        params.append(end_date)
    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    if not filters:
        market_query = """
            SELECT period, review_count, positive_reviews, negative_reviews, positive_ratio
            FROM mv_monthly_market_trends
            ORDER BY period
        """
    else:
        market_query = f"""
        SELECT
            to_char(date_trunc('month', r.collected_at), 'YYYY-MM') AS period,
            COUNT(*)::int AS review_count,
            COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::int AS positive_reviews,
            COUNT(*) FILTER (WHERE rs.sentiment_label = 'negative')::int AS negative_reviews,
            CASE
                WHEN COUNT(*) = 0 THEN 0
                ELSE (COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::float / COUNT(*)) * 100
            END AS positive_ratio
        FROM reviews r
        LEFT JOIN review_sentiments rs ON r.review_id = rs.review_id
        {where_clause}
        GROUP BY date_trunc('month', r.collected_at)
        ORDER BY date_trunc('month', r.collected_at)
        """
    top_genres_query = f"""
        SELECT COALESCE(NULLIF(g.genre, ''), 'Unknown') AS genre
        FROM reviews r
        JOIN games g ON g.app_id = r.app_id
        {where_clause}
        GROUP BY genre
        ORDER BY COUNT(*) DESC, genre ASC
        LIMIT %s
    """
    genre_series_query = f"""
        SELECT
            COALESCE(NULLIF(g.genre, ''), 'Unknown') AS genre,
            to_char(date_trunc('month', r.collected_at), 'YYYY-MM') AS period,
            COUNT(*)::int AS review_count,
            COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::int AS positive_reviews,
            COUNT(*) FILTER (WHERE rs.sentiment_label = 'negative')::int AS negative_reviews,
            CASE
                WHEN COUNT(*) = 0 THEN 0
                ELSE (COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::float / COUNT(*)) * 100
            END AS positive_ratio
        FROM reviews r
        JOIN games g ON g.app_id = r.app_id
        LEFT JOIN review_sentiments rs ON r.review_id = rs.review_id
        {where_clause}
            AND COALESCE(NULLIF(g.genre, ''), 'Unknown') = ANY(%s)
        GROUP BY genre, date_trunc('month', r.collected_at)
        ORDER BY genre, date_trunc('month', r.collected_at)
    """
    if not where_clause:
        genre_series_query = genre_series_query.replace("WHERE", "WHERE", 1).replace(
            "\n            AND COALESCE", "\n        WHERE COALESCE"
        )

    with db.cursor() as cursor:
        cursor.execute(market_query, params)
        market = cursor.fetchall()
        cursor.execute(top_genres_query, (*params, top_genres_limit))
        top_genres = [row["genre"] for row in cursor.fetchall()]
        cursor.execute(genre_series_query, (*params, top_genres))
        series_rows = cursor.fetchall()

    grouped = {genre: [] for genre in top_genres}
    for row in series_rows:
        genre = row.pop("genre")
        grouped.setdefault(genre, []).append(row)

    return {
        "market": market,
        "top_genres": [{"genre": genre, "data": data} for genre, data in grouped.items()],
    }


@router.get("/analysis/price-review", response_model=list[PriceReviewPoint])
def get_price_review_points(
    limit: int = Query(default=1000, ge=1, le=5000),
    db: connection = Depends(get_db),
) -> list[dict]:
    query = """
        SELECT
            game_id,
            name,
            genre,
            price,
            total_reviews,
            positive_ratio
        FROM mv_price_review_points
        ORDER BY total_reviews DESC, name ASC
        LIMIT %s
    """
    with db.cursor() as cursor:
        cursor.execute(query, (limit,))
        return cursor.fetchall()


@router.get("/analysis/genre-stats", response_model=GenreStatsResponse)
def get_genre_stats(
    limit: int = Query(default=30, ge=1, le=100),
    db: connection = Depends(get_db),
) -> dict:
    query = """
        WITH genre_values AS (
            SELECT
                trim(genre_value) AS genre,
                g.price,
                COALESCE(gaf.review_count, 0) AS review_count,
                COALESCE(gaf.sentiment_positive_ratio, 0) * 100 AS positive_ratio
            FROM games g
            LEFT JOIN game_analysis_features gaf ON g.app_id = gaf.app_id
            CROSS JOIN LATERAL regexp_split_to_table(COALESCE(g.genre, ''), ',') AS genre_value
        )
        SELECT
            genre,
            COUNT(*)::int AS game_count,
            COALESCE(AVG(price), 0)::float AS avg_price,
            COALESCE(AVG(review_count), 0)::float AS avg_review_count,
            COALESCE(AVG(positive_ratio), 0)::float AS avg_positive_ratio
        FROM genre_values
        WHERE genre <> ''
        GROUP BY genre
        ORDER BY game_count DESC, genre ASC
        LIMIT %s
    """
    with db.cursor() as cursor:
        cursor.execute(query, (limit,))
        return {"items": cursor.fetchall()}


@router.get("/analysis/price-band-stats", response_model=PriceBandStatsResponse)
def get_price_band_stats(db: connection = Depends(get_db)) -> dict:
    query = """
        WITH banded AS (
            SELECT
                CASE
                    WHEN COALESCE(g.price, 0) = 0 THEN 'Free'
                    WHEN g.price < 5000 THEN '0-5000'
                    WHEN g.price < 15000 THEN '5000-15000'
                    WHEN g.price < 30000 THEN '15000-30000'
                    ELSE '30000+'
                END AS price_band,
                CASE
                    WHEN COALESCE(g.price, 0) = 0 THEN 0
                    WHEN g.price < 5000 THEN 1
                    WHEN g.price < 15000 THEN 2
                    WHEN g.price < 30000 THEN 3
                    ELSE 4
                END AS sort_order,
                COALESCE(gaf.review_count, 0) AS review_count,
                COALESCE(gaf.sentiment_positive_ratio, 0) * 100 AS positive_ratio
            FROM games g
            LEFT JOIN game_analysis_features gaf ON g.app_id = gaf.app_id
        )
        SELECT
            price_band,
            COUNT(*)::int AS game_count,
            COALESCE(AVG(review_count), 0)::float AS avg_review_count,
            COALESCE(AVG(positive_ratio), 0)::float AS avg_positive_ratio
        FROM banded
        GROUP BY price_band, sort_order
        ORDER BY sort_order ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query)
        return {"items": cursor.fetchall()}


@router.get("/analysis/platform-stats", response_model=PlatformStatsResponse)
def get_platform_stats(db: connection = Depends(get_db)) -> dict:
    query = """
        WITH platform_games AS (
            SELECT 'Windows' AS platform, g.app_id, COALESCE(gaf.sentiment_positive_ratio, 0) * 100 AS positive_ratio
            FROM games g
            LEFT JOIN game_analysis_features gaf ON g.app_id = gaf.app_id
            WHERE g.is_windows IS TRUE
            UNION ALL
            SELECT 'Mac' AS platform, g.app_id, COALESCE(gaf.sentiment_positive_ratio, 0) * 100 AS positive_ratio
            FROM games g
            LEFT JOIN game_analysis_features gaf ON g.app_id = gaf.app_id
            WHERE g.is_mac IS TRUE
            UNION ALL
            SELECT 'Linux' AS platform, g.app_id, COALESCE(gaf.sentiment_positive_ratio, 0) * 100 AS positive_ratio
            FROM games g
            LEFT JOIN game_analysis_features gaf ON g.app_id = gaf.app_id
            WHERE g.is_linux IS TRUE
        )
        SELECT
            platform,
            COUNT(DISTINCT app_id)::int AS game_count,
            COALESCE(AVG(positive_ratio), 0)::float AS avg_positive_ratio
        FROM platform_games
        GROUP BY platform
        ORDER BY
            CASE platform
                WHEN 'Windows' THEN 1
                WHEN 'Mac' THEN 2
                WHEN 'Linux' THEN 3
                ELSE 4
            END
    """
    with db.cursor() as cursor:
        cursor.execute(query)
        return {"items": cursor.fetchall()}


@router.get("/analysis/genre-trends", response_model=GenreTrendsResponse)
def get_genre_trends(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=20),
    db: connection = Depends(get_db),
) -> dict:
    filters, params = date_filters("r", start_date, end_date)
    date_where = where_clause(filters)
    query = f"""
        WITH top_genres AS (
            SELECT COALESCE(NULLIF(g.genre, ''), 'Unknown') AS genre
            FROM reviews r
            JOIN games g ON g.app_id = r.app_id
            {date_where}
            GROUP BY genre
            ORDER BY COUNT(*) DESC, genre ASC
            LIMIT %s
        ),
        monthly AS (
            SELECT
                COALESCE(NULLIF(g.genre, ''), 'Unknown') AS genre,
                to_char(date_trunc('month', r.collected_at), 'YYYY-MM') AS period,
                COUNT(*)::int AS review_count,
                COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::int AS positive_reviews,
                COUNT(*) FILTER (WHERE rs.sentiment_label = 'negative')::int AS negative_reviews,
                CASE
                    WHEN COUNT(*) = 0 THEN 0
                    ELSE (COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::float / COUNT(*)) * 100
                END AS positive_ratio
            FROM reviews r
            JOIN games g ON g.app_id = r.app_id
            LEFT JOIN review_sentiments rs ON r.review_id = rs.review_id
            {date_where}
            GROUP BY genre, date_trunc('month', r.collected_at)
        ),
        ranked AS (
            SELECT monthly.*
            FROM monthly
            JOIN top_genres tg ON tg.genre = monthly.genre
        ),
        with_previous AS (
            SELECT
                *,
                LAG(review_count) OVER (PARTITION BY genre ORDER BY period) AS previous_review_count,
                LAG(positive_ratio) OVER (PARTITION BY genre ORDER BY period) AS previous_positive_ratio
            FROM ranked
        )
        SELECT
            genre,
            period,
            review_count,
            positive_reviews,
            negative_reviews,
            positive_ratio,
            CASE
                WHEN previous_review_count IS NULL OR previous_review_count = 0 THEN NULL
                ELSE ((review_count - previous_review_count)::float / previous_review_count) * 100
            END AS review_count_change_percent,
            CASE
                WHEN previous_positive_ratio IS NULL THEN NULL
                ELSE positive_ratio - previous_positive_ratio
            END AS positive_ratio_change_points
        FROM with_previous
        ORDER BY genre ASC, period ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query, (*params, limit, *params))
        return {"items": cursor.fetchall()}


@router.get("/analysis/price-trends", response_model=PriceTrendsResponse)
def get_price_trends(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: connection = Depends(get_db),
) -> dict:
    filters, params = date_filters("r", start_date, end_date)
    date_where = where_clause(filters)
    query = f"""
        WITH monthly AS (
            SELECT
                CASE
                    WHEN COALESCE(g.price, 0) = 0 THEN 'Free'
                    WHEN g.price < 5000 THEN '0-5000'
                    WHEN g.price < 15000 THEN '5000-15000'
                    WHEN g.price < 30000 THEN '15000-30000'
                    ELSE '30000+'
                END AS price_band,
                CASE
                    WHEN COALESCE(g.price, 0) = 0 THEN 0
                    WHEN g.price < 5000 THEN 1
                    WHEN g.price < 15000 THEN 2
                    WHEN g.price < 30000 THEN 3
                    ELSE 4
                END AS sort_order,
                to_char(date_trunc('month', r.collected_at), 'YYYY-MM') AS period,
                COUNT(*)::int AS review_count,
                COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::int AS positive_reviews,
                COUNT(*) FILTER (WHERE rs.sentiment_label = 'negative')::int AS negative_reviews,
                CASE
                    WHEN COUNT(*) = 0 THEN 0
                    ELSE (COUNT(*) FILTER (WHERE rs.sentiment_label = 'positive')::float / COUNT(*)) * 100
                END AS positive_ratio
            FROM reviews r
            JOIN games g ON g.app_id = r.app_id
            LEFT JOIN review_sentiments rs ON r.review_id = rs.review_id
            {date_where}
            GROUP BY price_band, sort_order, date_trunc('month', r.collected_at)
        ),
        with_previous AS (
            SELECT
                *,
                LAG(review_count) OVER (PARTITION BY price_band ORDER BY period) AS previous_review_count,
                LAG(positive_ratio) OVER (PARTITION BY price_band ORDER BY period) AS previous_positive_ratio
            FROM monthly
        )
        SELECT
            price_band,
            period,
            review_count,
            positive_reviews,
            negative_reviews,
            positive_ratio,
            CASE
                WHEN previous_review_count IS NULL OR previous_review_count = 0 THEN NULL
                ELSE ((review_count - previous_review_count)::float / previous_review_count) * 100
            END AS review_count_change_percent,
            CASE
                WHEN previous_positive_ratio IS NULL THEN NULL
                ELSE positive_ratio - previous_positive_ratio
            END AS positive_ratio_change_points
        FROM with_previous
        ORDER BY sort_order ASC, period ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query, params)
        return {"items": cursor.fetchall()}


@router.get("/analysis/topics/sentiment", response_model=TopicSentimentResponse)
def get_topic_sentiment(
    genre: str | None = Query(default=None),
    db: connection = Depends(get_db),
) -> dict:
    filters = []
    params = []
    if genre:
        filters.append("g.genre ILIKE %s")
        params.append(f"%{genre}%")
    filter_clause = "AND " + " AND ".join(filters) if filters else ""
    query = f"""
        WITH category_reviews AS (
            SELECT
                category_map.category,
                category_map.keywords,
                rs.sentiment_label
            FROM cleaned_reviews cr
            JOIN games g ON g.app_id = cr.app_id
            JOIN review_sentiments rs ON cr.review_id = rs.review_id
            CROSS JOIN ({TOPIC_CATEGORY_VALUES}) AS category_map(category, keywords)
            WHERE EXISTS (
                    SELECT 1
                    FROM unnest(category_map.keywords) keyword
                    WHERE lower(cr.clean_text) LIKE '%%' || keyword || '%%'
                )
                {filter_clause}
        )
        SELECT
            category,
            keywords,
            COUNT(*) FILTER (WHERE sentiment_label = 'positive')::int AS positive_count,
            COUNT(*) FILTER (WHERE sentiment_label = 'neutral')::int AS neutral_count,
            COUNT(*) FILTER (WHERE sentiment_label = 'negative')::int AS negative_count,
            COUNT(*)::int AS total_count,
            CASE WHEN COUNT(*) = 0 THEN 0 ELSE (COUNT(*) FILTER (WHERE sentiment_label = 'positive')::float / COUNT(*)) * 100 END AS positive_ratio,
            CASE WHEN COUNT(*) = 0 THEN 0 ELSE (COUNT(*) FILTER (WHERE sentiment_label = 'neutral')::float / COUNT(*)) * 100 END AS neutral_ratio,
            CASE WHEN COUNT(*) = 0 THEN 0 ELSE (COUNT(*) FILTER (WHERE sentiment_label = 'negative')::float / COUNT(*)) * 100 END AS negative_ratio
        FROM category_reviews
        GROUP BY category, keywords
        ORDER BY total_count DESC, category ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return {
        "topic_sentiment_available": False,
        "method": "keyword_category_fallback",
        "message": "Review-level topic mapping is not available yet; this response uses keyword-category matching.",
        "items": rows,
    }


@router.get("/analysis/topics/by-genre", response_model=GenreTopicsResponse)
def get_topics_by_genre(
    limit: int = Query(default=5, ge=1, le=20),
    db: connection = Depends(get_db),
) -> dict:
    query = """
        WITH genre_topics AS (
            SELECT
                trim(genre_value) AS genre,
                gt.topic_id,
                gt.topic_keywords,
                SUM(gt.topic_weight)::float AS weight,
                COUNT(DISTINCT gt.app_id)::int AS game_count,
                ROW_NUMBER() OVER (
                    PARTITION BY trim(genre_value)
                    ORDER BY SUM(gt.topic_weight) DESC, gt.topic_id ASC
                ) AS topic_rank
            FROM game_topics gt
            JOIN games g ON g.app_id = gt.app_id
            CROSS JOIN LATERAL regexp_split_to_table(COALESCE(g.genre, ''), ',') AS genre_value
            WHERE trim(genre_value) <> ''
            GROUP BY trim(genre_value), gt.topic_id, gt.topic_keywords
        )
        SELECT
            genre,
            topic_id,
            topic_keywords AS keywords,
            weight,
            game_count
        FROM genre_topics
        WHERE topic_rank <= %s
        ORDER BY genre ASC, weight DESC, topic_id ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()

    return {
        "topic_sentiment_available": False,
        "message": "Genre topic weights are based on game-level topics; review-level topic sentiment is not available yet.",
        "items": [
            {
                **row,
                "keywords": [keyword.strip() for keyword in row["keywords"].split(",") if keyword.strip()],
            }
            for row in rows
        ],
    }


@router.get("/analysis/release-year-stats", response_model=ReleaseYearStatsResponse)
def get_release_year_stats(
    start_year: int | None = Query(default=None, ge=1970, le=2100),
    end_year: int | None = Query(default=None, ge=1970, le=2100),
    db: connection = Depends(get_db),
) -> dict:
    filters = ["gaf.release_year IS NOT NULL"]
    params = []
    if start_year is not None:
        filters.append("gaf.release_year >= %s")
        params.append(start_year)
    if end_year is not None:
        filters.append("gaf.release_year <= %s")
        params.append(end_year)
    query = f"""
        SELECT
            gaf.release_year,
            COUNT(*)::int AS game_count,
            COALESCE(AVG(gaf.review_count), 0)::float AS avg_review_count,
            (COALESCE(AVG(gaf.sentiment_positive_ratio), 0) * 100)::float AS avg_positive_ratio
        FROM game_analysis_features gaf
        WHERE {" AND ".join(filters)}
        GROUP BY gaf.release_year
        ORDER BY gaf.release_year ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query, params)
        return {"items": cursor.fetchall()}


@router.get("/games/{game_id}/reviews/insights", response_model=ReviewInsightsResponse)
def get_review_insights(game_id: int, db: connection = Depends(get_db)) -> dict:
    query = """
        WITH category_reviews AS (
            SELECT
                category_map.category,
                category_map.keywords,
                rs.sentiment_label
            FROM cleaned_reviews cr
            JOIN review_sentiments rs ON cr.review_id = rs.review_id
            CROSS JOIN (
                VALUES
                    ('gameplay', ARRAY['gameplay', 'combat', 'mechanic', 'controls', 'fun']),
                    ('bugs', ARRAY['bug', 'crash', 'glitch', 'broken', 'error']),
                    ('graphics', ARRAY['graphics', 'visual', 'art', 'animation', 'beautiful']),
                    ('performance', ARRAY['performance', 'fps', 'lag', 'optimization', 'stutter']),
                    ('story', ARRAY['story', 'character', 'narrative', 'dialogue', 'ending']),
                    ('price', ARRAY['price', 'value', 'worth', 'expensive', 'cheap']),
                    ('multiplayer', ARRAY['multiplayer', 'coop', 'online', 'server', 'matchmaking'])
            ) AS category_map(category, keywords)
            WHERE cr.app_id = %s
                AND EXISTS (
                    SELECT 1
                    FROM unnest(category_map.keywords) keyword
                    WHERE lower(cr.clean_text) LIKE '%%' || keyword || '%%'
                )
        )
        SELECT
            category,
            keywords,
            COUNT(*) FILTER (WHERE sentiment_label = 'positive')::int AS positive_count,
            COUNT(*) FILTER (WHERE sentiment_label = 'negative')::int AS negative_count,
            COUNT(*) FILTER (WHERE sentiment_label = 'neutral')::int AS neutral_count,
            CASE
                WHEN COUNT(*) = 0 THEN 0
                ELSE COUNT(*) FILTER (WHERE sentiment_label = 'positive')::float / COUNT(*)
            END AS positive_ratio,
            CASE
                WHEN COUNT(*) = 0 THEN 0
                ELSE COUNT(*) FILTER (WHERE sentiment_label = 'negative')::float / COUNT(*)
            END AS negative_ratio
        FROM category_reviews
        GROUP BY category, keywords
        ORDER BY COUNT(*) DESC, category ASC
    """
    with db.cursor() as cursor:
        cursor.execute(query, (game_id,))
        rows = cursor.fetchall()

    return {
        "game_id": game_id,
        "topic_sentiment_available": False,
        "message": "Review-level topic mapping is not available yet.",
        "satisfaction_factors": sorted(rows, key=lambda row: row["positive_ratio"], reverse=True)[:5],
        "dissatisfaction_factors": sorted(rows, key=lambda row: row["negative_ratio"], reverse=True)[:5],
        "topics": rows,
    }


@router.get("/analysis/topics/clusters", response_model=TopicClusterResponse)
def get_topic_clusters(
    limit: int = Query(default=10, ge=1, le=30),
    db: connection = Depends(get_db),
) -> dict:
    query = """
        SELECT topic_id, topic_keywords, topic_weight
        FROM global_topics
        ORDER BY topic_weight DESC, topic_id ASC
        LIMIT %s
    """
    with db.cursor() as cursor:
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()

    nodes = []
    links = []
    seen_keywords = set()
    for row in rows:
        topic_id = row["topic_id"]
        topic_node_id = f"topic-{topic_id}"
        weight = float(row["topic_weight"] or 0)
        nodes.append(
            {
                "id": topic_node_id,
                "label": f"Topic {topic_id}",
                "weight": weight,
                "topic_id": topic_id,
            }
        )
        keywords = [keyword.strip() for keyword in row["topic_keywords"].split(",") if keyword.strip()]
        for keyword in keywords[:8]:
            keyword_id = f"keyword-{keyword.lower().replace(' ', '-')}"
            if keyword_id not in seen_keywords:
                seen_keywords.add(keyword_id)
                nodes.append({"id": keyword_id, "label": keyword, "weight": weight, "topic_id": topic_id})
            links.append({"source": topic_node_id, "target": keyword_id, "value": weight})

    return {"nodes": nodes, "links": links}
