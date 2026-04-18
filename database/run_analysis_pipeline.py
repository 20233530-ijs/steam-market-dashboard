import argparse

from review_analysis import analyze_reviews
from review_collect import collect_reviews
from review_preprocess import preprocess_reviews


def run_pipeline(app_ids=None, limit=None, max_pages=3, page_size=100, replace_existing=False):
    collect_reviews(app_ids=app_ids, limit=limit, max_pages=max_pages, page_size=page_size)
    preprocess_reviews(app_ids=app_ids, replace_existing=replace_existing)
    analyze_reviews(app_ids=app_ids)
    print("Analysis pipeline completed.")


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Steam review analysis pipeline.")
    parser.add_argument("--app-id", dest="app_ids", action="append", type=int, help="Specific app_id to process.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of games to collect.")
    parser.add_argument("--max-pages", type=int, default=3, help="Review pages per game.")
    parser.add_argument("--page-size", type=int, default=100, help="Reviews per page.")
    parser.add_argument("--replace-existing", action="store_true", help="Replace cleaned rows for selected reviews.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(
        app_ids=args.app_ids,
        limit=args.limit,
        max_pages=args.max_pages,
        page_size=args.page_size,
        replace_existing=args.replace_existing,
    )
