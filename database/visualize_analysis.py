import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from db_utils import ARTIFACTS_DIR, ensure_artifacts_dir
from db_utils import ARTIFACTS_DIR, ensure_artifacts_dir, get_connection

sns.set_theme(style="whitegrid")


def load_csv(filename):
    path = ARTIFACTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Required artifact not found: {path}")
    return pd.read_csv(path)


def plot_sentiment_distribution(sentiments, output_dir):
    counts = sentiments["sentiment_label"].value_counts().rename_axis("sentiment_label").reset_index(name="count")
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(data=counts, x="sentiment_label", y="count", palette="Set2", ax=ax)
    ax.set_title("Review Sentiment Distribution")
    ax.set_xlabel("Sentiment")
    ax.set_ylabel("Review Count")
    fig.tight_layout()
    fig.savefig(output_dir / "sentiment_distribution.png", dpi=200)
    plt.close(fig)


def plot_topic_weights(topics, output_dir):
    if topics.empty:
        return

    # games 테이블에서 app_id -> name 매핑 가져오기
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT app_id, name FROM games")
            name_map = {row[0]: row[1] for row in cursor.fetchall()}

    topics = topics.copy()
    topics["game_name"] = topics["app_id"].map(name_map).fillna(topics["app_id"].astype(str))
    topics["topic_label"] = topics["game_name"] + " / T" + topics["topic_id"].astype(str)
    top_topics = topics.sort_values("topic_weight", ascending=False).head(15)

    fig, ax = plt.subplots(figsize=(12, 7))
    sns.barplot(data=top_topics, x="topic_weight", y="topic_label", palette="Blues_r", ax=ax)
    ax.set_title("Top Game Topics by Weight")
    ax.set_xlabel("Average Topic Weight")
    ax.set_ylabel("Game / Topic")
    fig.tight_layout()
    fig.savefig(output_dir / "topic_weights.png", dpi=200)
    plt.close(fig)
"""def plot_topic_weights(topics, output_dir):
    if topics.empty:
        return

    topics = topics.copy()
    topics["topic_label"] = topics["name"].fillna(topics["app_id"].astype(str)) + " / T" + topics["topic_id"].astype(str)
    top_topics = topics.sort_values("topic_weight", ascending=False).head(15)

    fig, ax = plt.subplots(figsize=(12, 7))
    sns.barplot(data=top_topics, x="topic_weight", y="topic_label", palette="Blues_r", ax=ax)
    ax.set_title("Top Game Topics by Weight")
    ax.set_xlabel("Average Topic Weight")
    ax.set_ylabel("Game / Topic")
    fig.tight_layout()
    fig.savefig(output_dir / "topic_weights.png", dpi=200)
    plt.close(fig)"""


def plot_correlation_heatmap(features, output_dir):
    numeric_columns = [
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
    available = [column for column in numeric_columns if column in features.columns]
    if len(available) < 2:
        return

    correlation = features[available].corr(numeric_only=True)
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(correlation, annot=True, cmap="RdBu_r", center=0, fmt=".2f", ax=ax)
    ax.set_title("Game Feature Correlation Heatmap")
    fig.tight_layout()
    fig.savefig(output_dir / "feature_correlation_heatmap.png", dpi=200)
    plt.close(fig)


def plot_price_vs_popularity(features, output_dir):
    required = {"price", "popularity_score", "genre"}
    if not required.issubset(features.columns):
        return

    chart_data = features.copy()
    chart_data["price"] = chart_data["price"] / 100
    chart_data["primary_genre"] = chart_data["genre"].fillna("").apply(
        lambda value: value.split(",")[0].strip() if value else "Unknown"
    )
    top_genres = chart_data["primary_genre"].value_counts().head(6).index
    chart_data["primary_genre"] = chart_data["primary_genre"].where(
        chart_data["primary_genre"].isin(top_genres),
        "Other",
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.scatterplot(
        data=chart_data,
        x="price",
        y="popularity_score",
        hue="primary_genre",
        alpha=0.75,
        ax=ax,
    )
    ax.set_title("Price vs Popularity Score")
    ax.set_xlabel("Price")
    ax.set_ylabel("Popularity Score")
    fig.tight_layout()
    fig.savefig(output_dir / "price_vs_popularity.png", dpi=200)
    plt.close(fig)


def create_visualizations(output_dir=None):
    artifacts_dir = ensure_artifacts_dir()
    output_path = Path(output_dir) if output_dir else artifacts_dir
    output_path.mkdir(parents=True, exist_ok=True)

    sentiments = load_csv("review_sentiments.csv")
    topics = load_csv("game_topics.csv")
    features = load_csv("game_analysis_features.csv")

    plot_sentiment_distribution(sentiments, output_path)
    plot_topic_weights(topics, output_path)
    plot_correlation_heatmap(features, output_path)
    plot_price_vs_popularity(features, output_path)

    print(f"Saved visualization files to {output_path}.")


def parse_args():
    parser = argparse.ArgumentParser(description="Create charts from analysis CSV outputs.")
    parser.add_argument("--output-dir", default=None, help="Directory to store generated charts.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    create_visualizations(output_dir=args.output_dir)
