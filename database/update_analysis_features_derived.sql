ALTER TABLE game_analysis_features
    ADD COLUMN IF NOT EXISTS primary_genre VARCHAR(50),
    ADD COLUMN IF NOT EXISTS genre_count INTEGER,
    ADD COLUMN IF NOT EXISTS is_free BOOLEAN,
    ADD COLUMN IF NOT EXISTS price_bucket VARCHAR(20),
    ADD COLUMN IF NOT EXISTS release_year INTEGER,
    ADD COLUMN IF NOT EXISTS owners_bucket VARCHAR(20),
    ADD COLUMN IF NOT EXISTS popularity_rank_percent DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS sentiment_negative_ratio DOUBLE PRECISION;

UPDATE game_analysis_features gaf
SET
    primary_genre = NULLIF(TRIM(SPLIT_PART(COALESCE(g.genre, gaf.genre, ''), ',', 1)), ''),
    genre_count = CASE
        WHEN NULLIF(TRIM(COALESCE(g.genre, gaf.genre, '')), '') IS NULL THEN 0
        ELSE array_length(string_to_array(COALESCE(g.genre, gaf.genre, ''), ','), 1)
    END,
    is_free = COALESCE(gaf.price, 0) = 0,
    price_bucket = CASE
        WHEN COALESCE(gaf.price, 0) = 0 THEN 'free'
        WHEN gaf.price > 0 AND gaf.price <= 10000 THEN 'low'
        WHEN gaf.price > 10000 AND gaf.price <= 30000 THEN 'mid'
        WHEN gaf.price > 30000 THEN 'high'
        ELSE NULL
    END,
    release_year = CASE
        WHEN COALESCE(g.release_date, '') ~ '(19|20)[0-9]{2}'
        THEN substring(g.release_date FROM '(19|20)[0-9]{2}')::INTEGER
        ELSE NULL
    END,
    sentiment_negative_ratio = CASE
        WHEN COALESCE(gaf.review_count, 0) > 0
        THEN gaf.negative_review_count::DOUBLE PRECISION / gaf.review_count
        ELSE NULL
    END
FROM games g
WHERE g.app_id = gaf.app_id;

WITH ranked AS (
    SELECT
        app_id,
        PERCENT_RANK() OVER (ORDER BY popularity_score) AS rank_percent
    FROM game_analysis_features
    WHERE popularity_score IS NOT NULL
)
UPDATE game_analysis_features gaf
SET
    popularity_rank_percent = ranked.rank_percent,
    owners_bucket = CASE
        WHEN ranked.rank_percent >= 0.90 THEN 'top'
        WHEN ranked.rank_percent <= 0.10 THEN 'low'
        ELSE 'mid'
    END
FROM ranked
WHERE ranked.app_id = gaf.app_id;
