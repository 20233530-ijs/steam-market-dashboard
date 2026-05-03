from db_utils import get_connection


CREATE_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS games (
        app_id INTEGER PRIMARY KEY,
        name VARCHAR(200),
        genre VARCHAR(255),
        price INTEGER,
        release_date VARCHAR(50),
        developer VARCHAR(200),
        publisher VARCHAR(200),
        languages TEXT,
        tags TEXT
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
]


def initialize_database():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for statement in CREATE_TABLE_STATEMENTS:
                cursor.execute(statement)
            for statement in ALTER_TABLE_STATEMENTS:
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


if __name__ == "__main__":
    initialize_database()
