import argparse
import ast
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from gensim import corpora
from gensim.models import LdaModel
from nltk.sentiment import SentimentIntensityAnalyzer
from scipy.stats import pearsonr
from sklearn.preprocessing import StandardScaler

from db_setup_v2 import initialize_database
from db_utils import ARTIFACTS_DIR, ensure_artifacts_dir, get_connection


TOPIC_COUNT = 3
TOP_WORD_COUNT = 5
MIN_REVIEWS_PER_TOPIC_MODEL = 5
CLEANED_REVIEWS_CSV = ARTIFACTS_DIR / "cleaned_reviews.csv"


def parse_tokens(value):
    if isinstance(value, list):
        return value
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return ast.literal_eval(value)
    return list(value)


def parse_owner_range(owner_range):
    if not owner_range:
        return np.nan

    matches = re.findall(r"\d[\d,]*", owner_range)
    if len(matches) < 2:
        return np.nan

    low = int(matches[0].replace(",", ""))
    high = int(matches[1].replace(",", ""))
    return float((low + high) / 2)


def load_cleaned_reviews(app_ids=None):
    query = """
        SELECT
            cr.review_id,
            cr.app_id,
            cr.raw_text,
            cr.clean_text,
            cr.tokens,
            cr.token_count,
            g.name,
            g.genre,
            g.price,
            COALESCE(gs.owners, '') AS owners,
            COALESCE(gs.positive_reviews, 0) AS positive_reviews,
            COALESCE(gs.negative_reviews, 0) AS negative_reviews,
            COALESCE(gs.average_playtime, 0) AS average_playtime
        FROM cleaned_reviews cr
        JOIN games g ON g.app_id = cr.app_id
        LEFT JOIN (
            SELECT DISTINCT ON (app_id)
                app_id,
                owners,
                positive_reviews,
                negative_reviews,
                average_playtime
            FROM game_stats
            ORDER BY app_id, collected_at DESC
        ) gs ON gs.app_id = cr.app_id
    """
    params = ()
    if app_ids:
        query += " WHERE cr.app_id = ANY(%s)"
        params = (app_ids,)
    query += " ORDER BY cr.app_id, cr.review_id"

    with get_connection() as conn:
        dataframe = pd.read_sql_query(query, conn, params=params)

    if not dataframe.empty:
        dataframe["tokens"] = dataframe["tokens"].apply(parse_tokens)
    return dataframe


def load_cleaned_reviews_from_csv(app_ids=None):
    if not CLEANED_REVIEWS_CSV.exists():
        raise FileNotFoundError(f"Cleaned review CSV was not found: {CLEANED_REVIEWS_CSV}")

    dataframe = pd.read_csv(CLEANED_REVIEWS_CSV)
    if dataframe.empty:
        return dataframe

    dataframe["tokens"] = dataframe["tokens"].apply(parse_tokens)

    if app_ids:
        dataframe = dataframe[dataframe["app_id"].isin(app_ids)].copy()

    missing_columns = {"name", "genre", "price", "owners", "positive_reviews", "negative_reviews", "average_playtime"}
    if missing_columns.issubset(dataframe.columns):
        return dataframe

    # Fill game-level metadata from DB when the cleaned CSV only contains review-level fields.
    with get_connection() as conn:
        metadata = pd.read_sql_query(
            """
            SELECT
                g.app_id,
                g.name,
                g.genre,
                g.price,
                COALESCE(gs.owners, '') AS owners,
                COALESCE(gs.positive_reviews, 0) AS positive_reviews,
                COALESCE(gs.negative_reviews, 0) AS negative_reviews,
                COALESCE(gs.average_playtime, 0) AS average_playtime
            FROM games g
            LEFT JOIN (
                SELECT DISTINCT ON (app_id)
                    app_id,
                    owners,
                    positive_reviews,
                    negative_reviews,
                    average_playtime
                FROM game_stats
                ORDER BY app_id, collected_at DESC
            ) gs ON gs.app_id = g.app_id
            """,
            conn,
        )

    return dataframe.merge(metadata, on="app_id", how="left")


def resolve_input_dataframe(source="auto", app_ids=None):
    if source == "db":
        return load_cleaned_reviews(app_ids=app_ids)
    if source == "csv":
        return load_cleaned_reviews_from_csv(app_ids=app_ids)

    try:
        dataframe = load_cleaned_reviews(app_ids=app_ids)
        if not dataframe.empty:
            return dataframe
    except Exception:
        pass

    return load_cleaned_reviews_from_csv(app_ids=app_ids)


def ensure_vader():
    try:
        return SentimentIntensityAnalyzer()
    except LookupError as exc:
        raise RuntimeError(
            "NLTK VADER lexicon is missing. Run `python -m nltk.downloader vader_lexicon` before analysis."
        ) from exc


def run_sentiment_analysis(dataframe):
    analyzer = ensure_vader()
    sentiment_rows = []

    for row in dataframe.itertuples(index=False):
        scores = analyzer.polarity_scores(row.clean_text or row.raw_text or "")
        if scores["compound"] >= 0.05:
            label = "positive"
        elif scores["compound"] <= -0.05:
            label = "negative"
        else:
            label = "neutral"

        sentiment_rows.append(
            {
                "review_id": int(row.review_id),
                "app_id": int(row.app_id),
                "pos": float(scores["pos"]),
                "neu": float(scores["neu"]),
                "neg": float(scores["neg"]),
                "compound": float(scores["compound"]),
                "sentiment_label": label,
            }
        )

    return pd.DataFrame(sentiment_rows)


def run_topic_modeling(dataframe):
    topic_rows = []

    for app_id, group in dataframe.groupby("app_id"):
        documents = [tokens for tokens in group["tokens"] if len(tokens) >= 3]
        if len(documents) < MIN_REVIEWS_PER_TOPIC_MODEL:
            continue

        dictionary = corpora.Dictionary(documents)
        dictionary.filter_extremes(no_below=2, no_above=0.8)
        if len(dictionary) == 0:
            continue

        corpus = [dictionary.doc2bow(doc) for doc in documents]
        if not any(corpus):
            continue

        lda_model = LdaModel(
            corpus=corpus,
            id2word=dictionary,
            num_topics=min(TOPIC_COUNT, len(dictionary)),
            random_state=42,
            passes=10,
        )

        topic_distribution = lda_model.get_document_topics(corpus, minimum_probability=0.0)
        topic_weights = {topic_id: [] for topic_id in range(lda_model.num_topics)}
        for document_topics in topic_distribution:
            for topic_id, weight in document_topics:
                topic_weights[topic_id].append(weight)

        for topic_id in range(lda_model.num_topics):
            keywords = lda_model.show_topic(topic_id, topn=TOP_WORD_COUNT)
            keyword_text = ", ".join(word for word, _ in keywords)
            average_weight = float(np.mean(topic_weights[topic_id])) if topic_weights[topic_id] else 0.0
            topic_rows.append(
                {
                    "app_id": int(app_id),
                    "topic_id": int(topic_id),
                    "topic_keywords": keyword_text,
                    "topic_weight": average_weight,
                }
            )

    return pd.DataFrame(topic_rows)


def build_feature_dataframe(cleaned_df, sentiment_df):
    game_df = (
        cleaned_df[
            [
                "app_id",
                "name",
                "genre",
                "price",
                "owners",
                "positive_reviews",
                "negative_reviews",
                "average_playtime",
            ]
        ]
        .drop_duplicates(subset=["app_id"])
        .copy()
    )

    if game_df.empty:
        return game_df

    sentiment_summary = (
        sentiment_df.groupby("app_id")
        .agg(
            sentiment_compound_mean=("compound", "mean"),
            sentiment_positive_ratio=("sentiment_label", lambda series: float((series == "positive").mean())),
            review_count=("review_id", "count"),
        )
        .reset_index()
    )

    game_df = game_df.merge(sentiment_summary, on="app_id", how="left")
    game_df["owners_value"] = game_df["owners"].apply(parse_owner_range)
    game_df["positive_review_count"] = game_df["positive_reviews"].fillna(0).astype(int)
    game_df["negative_review_count"] = game_df["negative_reviews"].fillna(0).astype(int)
    game_df["review_count"] = game_df["review_count"].fillna(0).astype(int)
    game_df["price"] = game_df["price"].fillna(0).astype(float)
    game_df["log_price"] = np.log1p(game_df["price"])
    game_df["average_playtime"] = game_df["average_playtime"].fillna(0).astype(float)
    game_df["sentiment_compound_mean"] = game_df["sentiment_compound_mean"].fillna(0.0)
    game_df["sentiment_positive_ratio"] = game_df["sentiment_positive_ratio"].fillna(0.0)
    game_df["total_review_signal"] = (
        game_df["positive_review_count"] + game_df["negative_review_count"]
    ).astype(float)

    scaler_input = game_df[["owners_value", "total_review_signal", "average_playtime"]].fillna(0.0)
    scaled = StandardScaler().fit_transform(scaler_input)
    game_df["popularity_score"] = scaled.mean(axis=1)

    return game_df[
        [
            "app_id",
            "name",
            "genre",
            "price",
            "log_price",
            "owners_value",
            "review_count",
            "positive_review_count",
            "negative_review_count",
            "average_playtime",
            "sentiment_compound_mean",
            "sentiment_positive_ratio",
            "popularity_score",
        ]
    ]


def compute_correlations(feature_df):
    if feature_df.empty:
        return pd.DataFrame()

    split_genres = feature_df["genre"].fillna("").apply(
        lambda value: [genre.strip() for genre in value.split(",") if genre.strip()]
    )
    genre_dummies = split_genres.str.join("|").str.get_dummies(sep="|")
    genre_dummies.columns = [f"genre::{column}" for column in genre_dummies.columns]
    analysis_df = pd.concat(
        [
            feature_df[
                [
                    "app_id",
                    "log_price",
                    "owners_value",
                    "review_count",
                    "average_playtime",
                    "sentiment_compound_mean",
                    "sentiment_positive_ratio",
                    "popularity_score",
                ]
            ],
            genre_dummies,
        ],
        axis=1,
    )

    candidate_columns = [column for column in analysis_df.columns if column != "app_id"]
    correlation_rows = []

    for index, feature_a in enumerate(candidate_columns):
        for feature_b in candidate_columns[index + 1 :]:
            sample = analysis_df[[feature_a, feature_b]].dropna()
            if len(sample) < 2:
                continue

            if sample[feature_a].nunique() < 2 or sample[feature_b].nunique() < 2:
                continue

            correlation, p_value = pearsonr(sample[feature_a], sample[feature_b])
            if math.isnan(correlation) or math.isnan(p_value):
                continue

            correlation_rows.append(
                {
                    "feature_a": feature_a,
                    "feature_b": feature_b,
                    "correlation": float(correlation),
                    "p_value": float(p_value),
                    "sample_size": int(len(sample)),
                }
            )

    return pd.DataFrame(correlation_rows)


def save_sentiment_results(sentiment_df):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for row in sentiment_df.itertuples(index=False):
                cursor.execute(
                    """
                    INSERT INTO review_sentiments (
                        review_id,
                        app_id,
                        pos,
                        neu,
                        neg,
                        compound,
                        sentiment_label
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (review_id) DO UPDATE
                    SET
                        app_id = EXCLUDED.app_id,
                        pos = EXCLUDED.pos,
                        neu = EXCLUDED.neu,
                        neg = EXCLUDED.neg,
                        compound = EXCLUDED.compound,
                        sentiment_label = EXCLUDED.sentiment_label,
                        created_at = NOW()
                    """,
                    (
                        int(row.review_id),
                        int(row.app_id),
                        float(row.pos),
                        float(row.neu),
                        float(row.neg),
                        float(row.compound),
                        row.sentiment_label,
                    ),
                )
        conn.commit()


def save_topic_results(topic_df):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for row in topic_df.itertuples(index=False):
                cursor.execute(
                    """
                    INSERT INTO game_topics (
                        app_id,
                        topic_id,
                        topic_keywords,
                        topic_weight
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (app_id, topic_id) DO UPDATE
                    SET
                        topic_keywords = EXCLUDED.topic_keywords,
                        topic_weight = EXCLUDED.topic_weight,
                        created_at = NOW()
                    """,
                    (
                        int(row.app_id),
                        int(row.topic_id),
                        row.topic_keywords,
                        float(row.topic_weight),
                    ),
                )
        conn.commit()


def save_feature_results(feature_df):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for row in feature_df.itertuples(index=False):
                cursor.execute(
                    """
                    INSERT INTO game_analysis_features (
                        app_id,
                        name,
                        genre,
                        price,
                        log_price,
                        owners_value,
                        review_count,
                        positive_review_count,
                        negative_review_count,
                        average_playtime,
                        sentiment_compound_mean,
                        sentiment_positive_ratio,
                        popularity_score
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (app_id) DO UPDATE
                    SET
                        name = EXCLUDED.name,
                        genre = EXCLUDED.genre,
                        price = EXCLUDED.price,
                        log_price = EXCLUDED.log_price,
                        owners_value = EXCLUDED.owners_value,
                        review_count = EXCLUDED.review_count,
                        positive_review_count = EXCLUDED.positive_review_count,
                        negative_review_count = EXCLUDED.negative_review_count,
                        average_playtime = EXCLUDED.average_playtime,
                        sentiment_compound_mean = EXCLUDED.sentiment_compound_mean,
                        sentiment_positive_ratio = EXCLUDED.sentiment_positive_ratio,
                        popularity_score = EXCLUDED.popularity_score,
                        created_at = NOW()
                    """,
                    tuple(row),
                )
        conn.commit()


def save_correlation_results(correlation_df):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for row in correlation_df.itertuples(index=False):
                cursor.execute(
                    """
                    INSERT INTO correlation_results (
                        feature_a,
                        feature_b,
                        correlation,
                        p_value,
                        sample_size
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (feature_a, feature_b) DO UPDATE
                    SET
                        correlation = EXCLUDED.correlation,
                        p_value = EXCLUDED.p_value,
                        sample_size = EXCLUDED.sample_size,
                        created_at = NOW()
                    """,
                    (
                        row.feature_a,
                        row.feature_b,
                        float(row.correlation),
                        float(row.p_value),
                        int(row.sample_size),
                    ),
                )
        conn.commit()


def export_outputs(sentiment_df, topic_df, feature_df, correlation_df):
    artifacts_dir = ensure_artifacts_dir()
    sentiment_df.to_csv(artifacts_dir / "review_sentiments.csv", index=False, encoding="utf-8-sig")

    sentiment_summary = (
        feature_df[
            ["app_id", "name", "sentiment_compound_mean", "sentiment_positive_ratio", "review_count"]
        ].copy()
        if not feature_df.empty
        else pd.DataFrame(columns=["app_id", "name", "sentiment_compound_mean", "sentiment_positive_ratio", "review_count"])
    )
    sentiment_summary.to_csv(
        artifacts_dir / "game_sentiment_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    topic_df.to_csv(artifacts_dir / "game_topics.csv", index=False, encoding="utf-8-sig")
    feature_df.to_csv(artifacts_dir / "game_analysis_features.csv", index=False, encoding="utf-8-sig")
    correlation_df.to_csv(artifacts_dir / "correlation_results.csv", index=False, encoding="utf-8-sig")


def analyze_reviews(app_ids=None, source="auto"):
    initialize_database()
    cleaned_df = resolve_input_dataframe(source=source, app_ids=app_ids)
    if cleaned_df.empty:
        print("No cleaned reviews available. Run review_preprocess.py first.")
        return

    sentiment_df = run_sentiment_analysis(cleaned_df)
    topic_df = run_topic_modeling(cleaned_df)
    feature_df = build_feature_dataframe(cleaned_df, sentiment_df)
    correlation_df = compute_correlations(feature_df)

    save_sentiment_results(sentiment_df)
    save_topic_results(topic_df)
    save_feature_results(feature_df)
    save_correlation_results(correlation_df)
    export_outputs(sentiment_df, topic_df, feature_df, correlation_df)

    print(f"Saved {len(sentiment_df)} sentiment rows.")
    print(f"Saved {len(topic_df)} topic rows.")
    print(f"Saved {len(feature_df)} game feature rows.")
    print(f"Saved {len(correlation_df)} correlation rows.")


def parse_args():
    parser = argparse.ArgumentParser(description="Run sentiment, topic, and correlation analysis.")
    parser.add_argument("--app-id", dest="app_ids", action="append", type=int, help="Specific app_id to analyze.")
    parser.add_argument(
        "--source",
        choices=["auto", "db", "csv"],
        default="auto",
        help="Choose whether to read cleaned reviews from PostgreSQL or artifacts/cleaned_reviews.csv.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    analyze_reviews(app_ids=args.app_ids, source=args.source)
