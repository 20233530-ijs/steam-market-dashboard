import argparse
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_DIR = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if str(DATABASE_DIR) not in sys.path:
    sys.path.append(str(DATABASE_DIR))

from db_collect_all import collect_all_games
from db_utils import get_connection
from review_analysis import analyze_reviews
from review_collect import collect_reviews
from review_preprocess import preprocess_reviews
from visualize_analysis import create_visualizations

from collection.steam_api_collect import collect_steam_web_api_games
from collection.steam_store_details_collect import collect_steam_store_details


DEFAULT_STEPS = ["collect-games", "store-details", "collect-reviews", "preprocess", "analyze", "visualize"]
STEP_ALIASES = {
    "collect": ["collect-games", "store-details", "collect-reviews"],
}
logger = logging.getLogger(__name__)


def normalize_steps(steps):
    if not steps or "all" in steps:
        return DEFAULT_STEPS

    normalized_steps = []
    for step in steps:
        normalized_steps.extend(STEP_ALIASES.get(step, [step]))

    return list(dict.fromkeys(normalized_steps))


def mark_step_started(step):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO pipeline_runs (step, status)
                    VALUES (%s, 'running')
                    RETURNING run_id
                    """,
                    (step,),
                )
                run_id = cursor.fetchone()[0]
            conn.commit()
        return run_id
    except Exception:
        logger.debug("Could not record pipeline step start.", exc_info=True)
        return None


def mark_step_finished(run_id, status, message=None):
    if run_id is None:
        return

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE pipeline_runs
                    SET status = %s, finished_at = NOW(), message = %s
                    WHERE run_id = %s
                    """,
                    (status, message, run_id),
                )
            conn.commit()
    except Exception:
        logger.debug("Could not record pipeline step finish.", exc_info=True)


def run_step(step, callback):
    run_id = mark_step_started(step)
    logger.info("Starting step: %s", step)
    try:
        result = callback()
        mark_step_finished(run_id, "success")
        logger.info("Finished step: %s", step)
        return result
    except Exception as exc:
        mark_step_finished(run_id, "failed", str(exc))
        logger.exception("Pipeline step failed: %s", step)
        raise


def resolve_pipeline_app_ids(app_ids=None, limit=None, min_reviews=None):
    if app_ids:
        return app_ids
    if limit is None:
        return None

    review_threshold_filter = ""
    params = []
    if min_reviews is not None:
        review_threshold_filter = """
        WHERE COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0) >= %s
        """
        params.append(min_reviews)

    query = """
        WITH latest_stats AS (
            SELECT DISTINCT ON (app_id)
                app_id,
                COALESCE(positive_reviews, 0) AS positive_reviews,
                COALESCE(negative_reviews, 0) AS negative_reviews,
                collected_at
            FROM game_stats
            ORDER BY app_id, collected_at DESC, stat_id DESC
        )
        SELECT g.app_id
        FROM games g
        LEFT JOIN latest_stats ls ON ls.app_id = g.app_id
        {review_threshold_filter}
        ORDER BY
            COALESCE(ls.positive_reviews, 0) + COALESCE(ls.negative_reviews, 0) DESC,
            g.app_id ASC
        LIMIT %s
    """.format(review_threshold_filter=review_threshold_filter)
    params.append(limit)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, tuple(params))
            return [row[0] for row in cursor.fetchall()]


def run_pipeline(
    app_ids=None,
    limit=None,
    max_pages=5,
    page_size=100,
    game_limit=500,
    steamspy_request="all",
    steam_web_api_limit=1000,
    store_details_limit=500,
    min_reviews=None,
    replace_existing=False,
    export_full=False,
    skip_game_collection=False,
    skip_steam_web_api=False,
    skip_steamspy=False,
    skip_store_details=False,
    skip_visualizations=False,
    steps=None,
    workers=8,
    incremental=True,
):
    selected_steps = normalize_steps(steps)

    if "collect-games" in selected_steps:
        if not skip_game_collection:
            if not skip_steam_web_api:
                run_step(
                    "steam-web-api-seed",
                    lambda: collect_steam_web_api_games(game_limit=steam_web_api_limit),
                )
            else:
                logger.info("Skipping Steam Web API game seed collection.")

            if not skip_steamspy:
                run_step(
                    "steamspy-enrichment",
                    lambda: collect_all_games(limit=game_limit, request_name=steamspy_request),
                )
            else:
                logger.info("Skipping SteamSpy enrichment.")
        else:
            logger.info("Skipping all game collection; using games already in PostgreSQL.")

    target_app_ids = resolve_pipeline_app_ids(app_ids=app_ids, limit=limit, min_reviews=min_reviews)
    if target_app_ids:
        logger.info("Resolved %s app ids for collection, preprocessing, and analysis.", len(target_app_ids))
    elif limit is not None and min_reviews is not None:
        logger.warning("No app ids matched min_reviews=%s. Later steps may have no data to process.", min_reviews)

    if "store-details" in selected_steps and not skip_store_details:
        details_app_ids = target_app_ids
        if details_app_ids is None and store_details_limit is not None:
            logger.info("Enriching top %s games with Steam Store appdetails.", store_details_limit)
        else:
            logger.info("Enriching selected games with Steam Store appdetails.")
        run_step(
            "store-details",
            lambda: collect_steam_store_details(app_ids=details_app_ids, limit=store_details_limit),
        )
    elif "store-details" in selected_steps:
        logger.info("Skipping Steam Store appdetails enrichment.")

    if "collect-reviews" in selected_steps:
        run_step(
            "collect-reviews",
            lambda: collect_reviews(
                app_ids=target_app_ids,
                limit=None,
                max_pages=max_pages,
                page_size=page_size,
                workers=workers,
                incremental=incremental,
            ),
        )

    if "preprocess" in selected_steps:
        run_step(
            "preprocess",
            lambda: preprocess_reviews(
                app_ids=target_app_ids,
                replace_existing=replace_existing,
                export_full=export_full,
                incremental=incremental,
            ),
        )

    if "analyze" in selected_steps:
        run_step("analyze", lambda: analyze_reviews(app_ids=target_app_ids, incremental=incremental))

    if "visualize" in selected_steps and not skip_visualizations:
        run_step("visualize", create_visualizations)
    elif "visualize" in selected_steps:
        logger.info("Skipping visualization generation.")

    logger.info("Analysis pipeline completed.")


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Steam review analysis pipeline.")
    parser.add_argument("--app-id", dest="app_ids", action="append", type=int, help="Specific app_id to process.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of games to collect.")
    parser.add_argument(
        "--game-limit",
        type=int,
        default=500,
        help="Maximum number of SteamSpy games to store before review collection.",
    )
    parser.add_argument(
        "--steam-web-api-limit",
        type=int,
        default=1000,
        help="Maximum number of Steam Web API games to seed into the games table.",
    )
    parser.add_argument(
        "--store-details-limit",
        type=int,
        default=500,
        help="Maximum number of games to enrich from Steam Store appdetails when app ids are not explicitly resolved.",
    )
    parser.add_argument(
        "--steamspy-request",
        default="all",
        help="SteamSpy request name. Use 'all' for larger datasets or 'top100in2weeks' for a small sample.",
    )
    parser.add_argument("--max-pages", type=int, default=5, help="Review pages per game. Five pages targets about 500 reviews per game.")
    parser.add_argument("--page-size", type=int, default=100, help="Reviews per page.")
    parser.add_argument("--workers", type=int, default=8, help="Parallel workers for review API collection.")
    parser.add_argument(
        "--steps",
        nargs="+",
        choices=DEFAULT_STEPS + list(STEP_ALIASES.keys()) + ["all"],
        default=["all"],
        help="Pipeline steps to run. Use all for the full pipeline. Alias: collect = collect-games store-details collect-reviews.",
    )
    parser.add_argument("--replace-existing", action="store_true", help="Replace cleaned rows for selected reviews.")
    parser.add_argument("--export-full", action="store_true", help="Export full cleaned_reviews table to artifacts.")
    parser.add_argument(
        "--no-incremental",
        action="store_true",
        help="Disable incremental skip logic and reprocess selected data.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing data by keeping incremental skip logic enabled. This is the default behavior.",
    )
    parser.add_argument(
        "--min-reviews",
        type=int,
        default=None,
        help="Only select games whose latest SteamSpy positive+negative review count is at least this value.",
    )
    parser.add_argument(
        "--skip-game-collection",
        action="store_true",
        help="Use games already stored in PostgreSQL instead of refreshing SteamSpy top100 first.",
    )
    parser.add_argument(
        "--skip-steam-web-api",
        action="store_true",
        help="Skip Steam Web API app id/name seed collection.",
    )
    parser.add_argument(
        "--skip-steamspy",
        action="store_true",
        help="Skip SteamSpy metadata/stat enrichment.",
    )
    parser.add_argument(
        "--skip-store-details",
        action="store_true",
        help="Skip Steam Store appdetails metadata enrichment.",
    )
    parser.add_argument(
        "--skip-visualizations",
        action="store_true",
        help="Skip PNG chart generation after analysis CSV export.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    run_pipeline(
        app_ids=args.app_ids,
        limit=args.limit,
        max_pages=args.max_pages,
        page_size=args.page_size,
        game_limit=args.game_limit,
        steamspy_request=args.steamspy_request,
        steam_web_api_limit=args.steam_web_api_limit,
        store_details_limit=args.store_details_limit,
        min_reviews=args.min_reviews,
        replace_existing=args.replace_existing,
        export_full=args.export_full,
        skip_game_collection=args.skip_game_collection,
        skip_steam_web_api=args.skip_steam_web_api,
        skip_steamspy=args.skip_steamspy,
        skip_store_details=args.skip_store_details,
        skip_visualizations=args.skip_visualizations,
        steps=args.steps,
        workers=args.workers,
        incremental=not args.no_incremental,
    )
