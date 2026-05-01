import argparse

from db_collect_all import collect_all_games
from review_analysis import analyze_reviews
from review_collect import collect_reviews
from review_preprocess import preprocess_reviews
from visualize_analysis import create_visualizations


def run_pipeline(
    app_ids=None,
    limit=None,
    max_pages=3,
    page_size=100,
    replace_existing=False,
    skip_game_collection=False,
    skip_visualizations=False,
):
    if not skip_game_collection:
        collect_all_games()

    collect_reviews(app_ids=app_ids, limit=limit, max_pages=max_pages, page_size=page_size)
    preprocess_reviews(app_ids=app_ids, replace_existing=replace_existing)
    analyze_reviews(app_ids=app_ids)
    if not skip_visualizations:
        create_visualizations()
    print("Analysis pipeline completed.")


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Steam review analysis pipeline.")
    parser.add_argument("--app-id", dest="app_ids", action="append", type=int, help="Specific app_id to process.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of games to collect.")
    parser.add_argument("--max-pages", type=int, default=3, help="Review pages per game.")
    parser.add_argument("--page-size", type=int, default=100, help="Reviews per page.")
    parser.add_argument("--replace-existing", action="store_true", help="Replace cleaned rows for selected reviews.")
    parser.add_argument(
        "--skip-game-collection",
        action="store_true",
        help="Use games already stored in PostgreSQL instead of refreshing SteamSpy top100 first.",
    )
    parser.add_argument(
        "--skip-visualizations",
        action="store_true",
        help="Skip PNG chart generation after analysis CSV export.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(
        app_ids=args.app_ids,
        limit=args.limit,
        max_pages=args.max_pages,
        page_size=args.page_size,
        replace_existing=args.replace_existing,
        skip_game_collection=args.skip_game_collection,
        skip_visualizations=args.skip_visualizations,
    )
