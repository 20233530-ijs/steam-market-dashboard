import argparse
import os
import time
from urllib.parse import urlencode

import requests


def timed_get(base_url: str, path: str, params: dict | None = None, headers: dict | None = None) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    started_at = time.perf_counter()
    response = requests.get(url, params=params, headers=headers, timeout=30)
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    response.raise_for_status()
    payload = response.json()
    query = f"?{urlencode(params)}" if params else ""
    print(f"GET {path}{query} -> {response.status_code} in {elapsed_ms:.2f} ms")
    return payload


def verify_games_pagination(base_url: str) -> None:
    first_page = timed_get(
        base_url,
        "/games",
        {"limit": 10, "sort": "reviews", "order": "desc", "include_total": "true"},
    )
    first_ids = [item["game_id"] for item in first_page["items"]]
    print(f"first page ids: {first_ids}")

    next_cursor = first_page.get("next_cursor")
    if not next_cursor:
        print("next_cursor is empty; dataset may have <= limit rows.")
        return

    second_page = timed_get(
        base_url,
        "/games",
        {
            "limit": 10,
            "sort": "reviews",
            "order": "desc",
            "cursor_value": next_cursor["cursor_value"],
            "cursor_id": next_cursor["cursor_id"],
        },
    )
    second_ids = [item["game_id"] for item in second_page["items"]]
    overlap = set(first_ids).intersection(second_ids)
    if overlap:
        raise AssertionError(f"Cursor pagination returned duplicate game ids: {sorted(overlap)}")
    print(f"second page ids: {second_ids}")


def verify_distribution(base_url: str) -> None:
    payload = timed_get(
        base_url,
        "/games",
        {
            "limit": 10,
            "genre": "RPG",
            "min_positive_ratio": 70,
            "include_total": "true",
            "include_distribution": "true",
        },
    )
    distribution_total = sum(item["count"] for item in payload["genre_distribution"])
    print(f"filtered total_count: {payload['total_count']}")
    print(f"genre distribution total: {distribution_total}")
    if payload["total_count"] is not None and distribution_total > payload["total_count"]:
        raise AssertionError("Genre distribution exceeds total_count.")


def verify_reference_endpoints(base_url: str) -> None:
    timed_get(base_url, "/genres")
    timed_get(base_url, "/analysis/trends")
    timed_get(base_url, "/analysis/price-review", {"limit": 50})
    timed_get(base_url, "/games/rankings", {"metric": "reviews", "limit": 10})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify API behavior against a running backend and real PostgreSQL DB.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("API_BASE_URL"),
        help=(
            "API origin to verify. Can also be provided with API_BASE_URL. "
            "Use the URL provided by the deployment owner."
        ),
    )
    args = parser.parse_args()
    if not args.base_url:
        parser.error("--base-url or API_BASE_URL is required")
    return args


if __name__ == "__main__":
    args = parse_args()
    verify_games_pagination(args.base_url)
    verify_distribution(args.base_url)
    verify_reference_endpoints(args.base_url)
    print("Real DB API verification completed.")
