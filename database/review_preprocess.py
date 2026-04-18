import argparse
import json
import re

import pandas as pd
import spacy

from db_setup_v2 import initialize_database
from db_utils import ensure_artifacts_dir, get_connection


MIN_TOKEN_COUNT = 3


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


def fetch_reviews(app_ids=None):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if app_ids:
                cursor.execute(
                    """
                    SELECT review_id, app_id, review_text, language
                    FROM reviews
                    WHERE app_id = ANY(%s) AND language = 'english'
                    ORDER BY review_id
                    """,
                    (app_ids,),
                )
            else:
                cursor.execute(
                    """
                    SELECT review_id, app_id, review_text, language
                    FROM reviews
                    WHERE language = 'english'
                    ORDER BY review_id
                    """
                )
            return cursor.fetchall()


def store_cleaned_reviews(rows, replace_existing=False):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if replace_existing and rows:
                review_ids = [row["review_id"] for row in rows]
                cursor.execute(
                    "DELETE FROM cleaned_reviews WHERE review_id = ANY(%s)",
                    (review_ids,),
                )

            for row in rows:
                cursor.execute(
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
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
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
                    (
                        row["review_id"],
                        row["app_id"],
                        row["raw_text"],
                        row["clean_text"],
                        json.dumps(row["tokens"]),
                        row["token_count"],
                        row["language"],
                    ),
                )
        conn.commit()


def export_cleaned_reviews(rows):
    artifacts_dir = ensure_artifacts_dir()
    output_path = artifacts_dir / "cleaned_reviews.csv"
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Saved cleaned dataset to {output_path}.")


def preprocess_reviews(app_ids=None, replace_existing=False):
    initialize_database()
    nlp = load_nlp()
    source_rows = fetch_reviews(app_ids=app_ids)

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

    store_cleaned_reviews(cleaned_rows, replace_existing=replace_existing)
    export_cleaned_reviews(cleaned_rows)
    print(f"Preprocessed {len(cleaned_rows)} reviews.")
    return cleaned_rows


def parse_args():
    parser = argparse.ArgumentParser(description="Clean Steam reviews with spaCy.")
    parser.add_argument("--app-id", dest="app_ids", action="append", type=int, help="Specific app_id to preprocess.")
    parser.add_argument("--replace-existing", action="store_true", help="Replace cleaned rows for selected reviews.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    preprocess_reviews(app_ids=args.app_ids, replace_existing=args.replace_existing)
