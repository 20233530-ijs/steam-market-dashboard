from db_utils import get_connection


CREATE_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS games (
        app_id INTEGER PRIMARY KEY,
        name VARCHAR(200),
        genre VARCHAR(255),
        price INTEGER,
        is_free BOOLEAN,
        release_date VARCHAR(50),
        developer VARCHAR(200),
        publisher VARCHAR(200),
        languages TEXT,
        tags TEXT,
        header_image VARCHAR(500),
        capsule_image VARCHAR(500),
        website VARCHAR(500),
        is_windows BOOLEAN,
        is_mac BOOLEAN,
        is_linux BOOLEAN,
        metacritic_score INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_stats (
        stat_id SERIAL PRIMARY KEY,
        app_id INTEGER REFERENCES games(app_id),
        owners VARCHAR(50),
        positive_reviews INTEGER,
        negative_reviews INTEGER,
        average_playtime INTEGER,
        peak_players INTEGER,
        collected_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reviews (
        review_id SERIAL PRIMARY KEY,
        steam_review_id BIGINT UNIQUE NOT NULL,
        app_id INTEGER REFERENCES games(app_id),
        review_text TEXT,
        voted_up BOOLEAN,
        playtime_hours INTEGER,
        language VARCHAR(20) DEFAULT 'english',
        collected_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cleaned_reviews (
        review_id INTEGER PRIMARY KEY REFERENCES reviews(review_id) ON DELETE CASCADE,
        app_id INTEGER REFERENCES games(app_id),
        raw_text TEXT NOT NULL,
        clean_text TEXT NOT NULL,
        tokens JSONB NOT NULL,
        token_count INTEGER NOT NULL,
        language VARCHAR(20) DEFAULT 'english',
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_sentiments (
        review_id INTEGER PRIMARY KEY REFERENCES reviews(review_id) ON DELETE CASCADE,
        app_id INTEGER REFERENCES games(app_id),
        pos DOUBLE PRECISION NOT NULL,
        neu DOUBLE PRECISION NOT NULL,
        neg DOUBLE PRECISION NOT NULL,
        compound DOUBLE PRECISION NOT NULL,
        sentiment_label VARCHAR(20) NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_topics (
        topic_result_id SERIAL PRIMARY KEY,
        app_id INTEGER REFERENCES games(app_id),
        topic_id INTEGER NOT NULL,
        topic_keywords TEXT NOT NULL,
        topic_weight DOUBLE PRECISION NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (app_id, topic_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS global_topics (
        topic_id INTEGER PRIMARY KEY,
        topic_keywords TEXT NOT NULL,
        topic_weight DOUBLE PRECISION NOT NULL,
        sample_size INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_analysis_features (
        app_id INTEGER PRIMARY KEY REFERENCES games(app_id),
        name VARCHAR(200),
        genre VARCHAR(255),
        price INTEGER,
        log_price DOUBLE PRECISION,
        owners_value DOUBLE PRECISION,
        review_count INTEGER,
        positive_review_count INTEGER,
        negative_review_count INTEGER,
        average_playtime DOUBLE PRECISION,
        sentiment_compound_mean DOUBLE PRECISION,
        sentiment_positive_ratio DOUBLE PRECISION,
        popularity_score DOUBLE PRECISION,
        primary_genre VARCHAR(50),
        genre_count INTEGER,
        is_free BOOLEAN,
        price_bucket VARCHAR(20),
        release_year INTEGER,
        owners_bucket VARCHAR(20),
        popularity_rank_percent DOUBLE PRECISION,
        sentiment_negative_ratio DOUBLE PRECISION,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS correlation_results (
        correlation_id SERIAL PRIMARY KEY,
        feature_a VARCHAR(100) NOT NULL,
        feature_b VARCHAR(100) NOT NULL,
        correlation DOUBLE PRECISION NOT NULL,
        p_value DOUBLE PRECISION NOT NULL,
        sample_size INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE (feature_a, feature_b)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id SERIAL PRIMARY KEY,
        step VARCHAR(100) NOT NULL,
        status VARCHAR(20) NOT NULL,
        started_at TIMESTAMP DEFAULT NOW(),
        finished_at TIMESTAMP,
        message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_wishlist (
        user_key VARCHAR(100) NOT NULL,
        app_id INTEGER NOT NULL REFERENCES games(app_id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (user_key, app_id)
    )
    """,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS game_price_history (
        price_history_id SERIAL PRIMARY KEY,
        app_id INTEGER NOT NULL REFERENCES games(app_id) ON DELETE CASCADE,
        price INTEGER,
        discount_percent INTEGER,
        final_price INTEGER,
        collected_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_topics (
        review_id INTEGER REFERENCES reviews(review_id) ON DELETE CASCADE,
        topic_id INTEGER NOT NULL,
        topic_weight DOUBLE PRECISION NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (review_id, topic_id)
    )
    """,
]


ALTER_TABLE_STATEMENTS = [
    """
    ALTER TABLE game_analysis_features
        ADD COLUMN IF NOT EXISTS primary_genre VARCHAR(50),
        ADD COLUMN IF NOT EXISTS genre_count INTEGER,
        ADD COLUMN IF NOT EXISTS is_free BOOLEAN,
        ADD COLUMN IF NOT EXISTS price_bucket VARCHAR(20),
        ADD COLUMN IF NOT EXISTS release_year INTEGER,
        ADD COLUMN IF NOT EXISTS owners_bucket VARCHAR(20),
        ADD COLUMN IF NOT EXISTS popularity_rank_percent DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS sentiment_negative_ratio DOUBLE PRECISION
    """,
    """
    ALTER TABLE games
        ADD COLUMN IF NOT EXISTS is_free BOOLEAN,
        ADD COLUMN IF NOT EXISTS header_image VARCHAR(500),
        ADD COLUMN IF NOT EXISTS capsule_image VARCHAR(500),
        ADD COLUMN IF NOT EXISTS website VARCHAR(500),
        ADD COLUMN IF NOT EXISTS is_windows BOOLEAN,
        ADD COLUMN IF NOT EXISTS is_mac BOOLEAN,
        ADD COLUMN IF NOT EXISTS is_linux BOOLEAN,
        ADD COLUMN IF NOT EXISTS metacritic_score INTEGER
    """,
]


CREATE_INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_games_genre ON games (genre)",
    "CREATE INDEX IF NOT EXISTS idx_games_price ON games (price)",
    "CREATE INDEX IF NOT EXISTS idx_games_release_date ON games (release_date)",
    "CREATE INDEX IF NOT EXISTS idx_games_is_free ON games (is_free)",
    "CREATE INDEX IF NOT EXISTS idx_games_metacritic_score ON games (metacritic_score)",
    "CREATE INDEX IF NOT EXISTS idx_game_analysis_features_review_count ON game_analysis_features (review_count)",
    "CREATE INDEX IF NOT EXISTS idx_game_analysis_features_positive_ratio ON game_analysis_features (sentiment_positive_ratio)",
    "CREATE INDEX IF NOT EXISTS idx_game_analysis_features_is_free ON game_analysis_features (is_free)",
    "CREATE INDEX IF NOT EXISTS idx_game_stats_app_collected ON game_stats (app_id, collected_at DESC, stat_id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_game_stats_app_collected_simple ON game_stats (app_id, collected_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_game_topics_app_topic ON game_topics (app_id, topic_id)",
    "CREATE INDEX IF NOT EXISTS idx_review_topics_review_topic ON review_topics (review_id, topic_id)",
    "CREATE INDEX IF NOT EXISTS idx_game_price_history_app_collected ON game_price_history (app_id, collected_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_user_wishlist_user_key ON user_wishlist (user_key)",
    "CREATE INDEX IF NOT EXISTS idx_user_notifications_user_key_created ON user_notifications (user_key, created_at DESC)",
]


CREATE_MATERIALIZED_VIEW_STATEMENTS = [
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS mv_monthly_market_trends AS
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
    GROUP BY date_trunc('month', r.collected_at)
    """,
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS mv_price_review_points AS
    SELECT
        g.app_id AS game_id,
        g.name,
        g.genre,
        g.price,
        COALESCE(gaf.review_count, COALESCE(gs.positive_reviews, 0) + COALESCE(gs.negative_reviews, 0), 0) AS total_reviews,
        CASE
            WHEN COALESCE(gaf.review_count, COALESCE(gs.positive_reviews, 0) + COALESCE(gs.negative_reviews, 0), 0) > 0
                THEN (
                    COALESCE(gaf.positive_review_count, gs.positive_reviews, 0)::float
                    / COALESCE(gaf.review_count, COALESCE(gs.positive_reviews, 0) + COALESCE(gs.negative_reviews, 0), 0)
                ) * 100
            ELSE COALESCE(gaf.sentiment_positive_ratio, 0) * 100
        END AS positive_ratio
    FROM games g
    LEFT JOIN game_analysis_features gaf ON g.app_id = gaf.app_id
    LEFT JOIN LATERAL (
        SELECT positive_reviews, negative_reviews
        FROM game_stats
        WHERE app_id = g.app_id
        ORDER BY collected_at DESC, stat_id DESC
        LIMIT 1
    ) gs ON TRUE
    """,
]


CREATE_MATERIALIZED_VIEW_INDEX_STATEMENTS = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_monthly_market_trends_period ON mv_monthly_market_trends (period)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_price_review_points_game_id ON mv_price_review_points (game_id)",
    "CREATE INDEX IF NOT EXISTS idx_mv_price_review_points_reviews ON mv_price_review_points (total_reviews DESC)",
]


def initialize_database():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for statement in CREATE_TABLE_STATEMENTS:
                cursor.execute(statement)
            for statement in ALTER_TABLE_STATEMENTS:
                cursor.execute(statement)
            for statement in CREATE_INDEX_STATEMENTS:
                cursor.execute(statement)
            for statement in CREATE_MATERIALIZED_VIEW_STATEMENTS:
                cursor.execute(statement)
            for statement in CREATE_MATERIALIZED_VIEW_INDEX_STATEMENTS:
                cursor.execute(statement)
        conn.commit()

    print("Database schema is ready.")
    print("- games")
    print("- game_stats")
    print("- reviews")
    print("- cleaned_reviews")
    print("- review_sentiments")
    print("- game_topics")
    print("- global_topics")
    print("- game_analysis_features")
    print("- correlation_results")
    print("- pipeline_runs")
    print("- user_wishlist")
    print("- user_notifications")
    print("- game_price_history")
    print("- mv_monthly_market_trends")
    print("- mv_price_review_points")


if __name__ == "__main__":
    initialize_database()
