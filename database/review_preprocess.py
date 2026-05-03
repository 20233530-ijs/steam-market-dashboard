import argparse
import json
import logging
import re

import pandas as pd
import spacy
from psycopg2.extras import execute_values
from sqlalchemy import text

from db_setup_v2 import initialize_database
from db_utils import ensure_artifacts_dir, get_connection, get_engine


MIN_TOKEN_COUNT = 3
logger = logging.getLogger(__name__)


def load_nlp():
    try:
        return spacy.load("en_core_web_sm", disable=["parser", "ner"])
    except OSError:
        print("spaCy model 'en_core_web_sm' is not installed. Falling back to blank English tokenizer.")
        return spacy.blank("en")


def clean_and_tokenize(text, nlp):
    normalized = re.sub(r"[^A-Za-z\s]", " ", text or "")
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    if not normalized:
        return "", []

    doc = nlp(normalized)
    tokens = [
        token.text
        for token in doc
        if token.text.isalpha() and not token.is_stop and len(token.text) > 1
    ]
    clean_text = " ".join(tokens)
    return clean_text, tokens


def fetch_reviews(app_ids=None, incremental=True):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            incremental_join = ""
            incremental_filter = ""
            if incremental:
                incremental_join = "LEFT JOIN cleaned_reviews cr ON cr.review_id = r.review_id"
                incremental_filter = "AND cr.review_id IS NULL"

            if app_ids:
                cursor.execute(
                    f"""
                    SELECT r.review_id, r.app_id, r.review_text, r.language
                    FROM reviews r
                    {incremental_join}
                    WHERE r.app_id = ANY(%s)
                      AND r.language = 'english'
                      {incremental_filter}
                    ORDER BY r.review_id
                    """,
                    (app_ids,),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT r.review_id, r.app_id, r.review_text, r.language
                    FROM reviews r
                    {incremental_join}
                    WHERE r.language = 'english'
                      {incremental_filter}
                    ORDER BY r.review_id
                    """
                )
            return cursor.fetchall()


def store_cleaned_reviews(rows, replace_existing=False):
    if not rows:
        return 0

    values = [
        (
            row["review_id"],
            row["app_id"],
            row["raw_text"],
            row["clean_text"],
            json.dumps(row["tokens"]),
            row["token_count"],
            row["language"],
        )
        for row in rows
    ]

    with get_connection() as conn:
        with conn.cursor() as cursor:
            if replace_existing and rows:
                review_ids = [row["review_id"] for row in rows]
                cursor.execute(
                    "DELETE FROM cleaned_reviews WHERE review_id = ANY(%s)",
                    (review_ids,),
                )

            execute_values(
                cursor,
                """
                INSERT INTO cleaned_reviews (
                    review_id,
                    app_id,
                    raw_text,
                    clean_text,
                    tokens,
                    token_count,
                    language
                )
                VALUES %s
                ON CONFLICT (review_id) DO UPDATE
                SET
                    app_id = EXCLUDED.app_id,
                    raw_text = EXCLUDED.raw_text,
                    clean_text = EXCLUDED.clean_text,
                    tokens = EXCLUDED.tokens,
                    token_count = EXCLUDED.token_count,
                    language = EXCLUDED.language,
                    created_at = NOW()
                """,
                values,
                template="(%s, %s, %s, %s, %s::jsonb, %s, %s)",
                page_size=1000,
            )
        conn.commit()
    return len(rows)


def export_cleaned_reviews(rows):
    if not rows:
        logger.info("No new cleaned reviews to export.")
        return

    artifacts_dir = ensure_artifacts_dir()
    partial_path = artifacts_dir / "cleaned_reviews_partial.csv"
    legacy_path = artifacts_dir / "cleaned_reviews.csv"
    dataframe = pd.DataFrame(rows)
    dataframe.to_csv(partial_path, index=False, encoding="utf-8-sig")
    dataframe.to_csv(legacy_path, index=False, encoding="utf-8-sig")
    logger.info("Saved partial cleaned dataset to %s.", partial_path)


def export_full_cleaned_reviews():
    artifacts_dir = ensure_artifacts_dir()
    output_path = artifacts_dir / "cleaned_reviews_full.csv"
    with get_engine().connect() as conn:
        dataframe = pd.read_sql_query(
            text(
                """
            SELECT
                review_id,
                app_id,
                raw_text,
                clean_text,
                tokens,
                token_count,
                language,
                created_at
            FROM cleaned_reviews
            ORDER BY app_id, review_id
            """,
            ),
            conn,
        )
    dataframe.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info("Saved full cleaned dataset to %s.", output_path)
    return dataframe


def preprocess_reviews(app_ids=None, replace_existing=False, export_full=False, incremental=True):
    initialize_database()
    nlp = load_nlp()
    source_rows = fetch_reviews(app_ids=app_ids, incremental=(incremental and not replace_existing))
    logger.info("Selected %s reviews for preprocessing.", len(source_rows))

    cleaned_rows = []
    for review_id, app_id, review_text, language in source_rows:
        clean_text, tokens = clean_and_tokenize(review_text, nlp)
        if len(tokens) < MIN_TOKEN_COUNT:
            continue

        cleaned_rows.append(
            {
                "review_id": review_id,
                "app_id": app_id,
                "raw_text": review_text,
                "clean_text": clean_text,
                "tokens": tokens,
                "token_count": len(tokens),
                "language": language or "english",
            }
        )

    stored_count = store_cleaned_reviews(cleaned_rows, replace_existing=replace_existing)
    export_cleaned_reviews(cleaned_rows)
    if export_full:
        export_full_cleaned_reviews()
    logger.info("Preprocessed and stored %s reviews.", stored_count)
    return cleaned_rows


def parse_args():
    parser = argparse.ArgumentParser(description="Clean Steam reviews with spaCy.")
    parser.add_argument("--app-id", dest="app_ids", action="append", type=int, help="Specific app_id to preprocess.")
    parser.add_argument("--replace-existing", action="store_true", help="Replace cleaned rows for selected reviews.")
    parser.add_argument("--export-full", action="store_true", help="Export all cleaned reviews from DB.")
    parser.add_argument("--no-incremental", action="store_true", help="Preprocess reviews even if cleaned rows already exist.")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    preprocess_reviews(
        app_ids=args.app_ids,
        replace_existing=args.replace_existing,
        export_full=args.export_full,
        incremental=not args.no_incremental,
    )
