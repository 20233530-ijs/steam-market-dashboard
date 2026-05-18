# Steam Market Dashboard API

Base URL is environment-specific and should be provided by the deployment owner.

Recommended frontend configuration:

```env
API_BASE_URL=<provided-api-origin>
```

Examples:

- Local backend during development: `http://127.0.0.1:8000`
- Staging or production: use the URL provided by the deployment owner

Do not hardcode the local URL in frontend source code.

## Search Games

```http
GET /games
```

Use this endpoint for the search/list screen. By default it returns a fast list response without total count or chart distributions.

### Query Parameters

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `search` | string | null | Searches name, genre, tags, developer, and publisher. |
| `genre` | string | null | Filters games whose genre contains this value. |
| `min_price` | number | null | Minimum price in Steam cents. |
| `max_price` | number | null | Maximum price in Steam cents. |
| `is_free` | boolean | null | Filters free or paid games. |
| `min_positive_ratio` | number | null | Minimum positive ratio, 0-100. |
| `min_reviews` | integer | null | Minimum total review count. |
| `sort` | string | `reviews` | One of `reviews`, `positive_ratio`, `price`, `release_date`. |
| `order` | string | `desc` | One of `asc`, `desc`. |
| `limit` | integer | `50` | Capped at `100`. |
| `cursor_value` | string | null | Value from `next_cursor.cursor_value`. |
| `cursor_id` | integer | null | Value from `next_cursor.cursor_id`. |
| `include_total` | boolean | `false` | Enables `COUNT(*)` and returns `total_count`. |
| `include_distribution` | boolean | `false` | Enables chart distribution aggregation. |

### Fast List Example

```http
GET /games?search=elden&genre=RPG&min_positive_ratio=80&limit=20
```

Response:

```json
{
  "items": [
    {
      "game_id": 1245620,
      "name": "ELDEN RING",
      "genre": "Action, RPG",
      "price": 5999,
      "is_free": false,
      "owners": "10,000,000 .. 20,000,000",
      "positive_reviews": 500000,
      "negative_reviews": 50000,
      "total_reviews": 550000,
      "positive_ratio": 90.9,
      "average_playtime": 3600
    }
  ],
  "total_count": null,
  "page": 1,
  "limit": 20,
  "next_cursor": {
    "cursor_value": "550000",
    "cursor_id": 1245620
  },
  "genre_distribution": [],
  "positive_ratio_distribution": []
}
```

### Keyset Pagination

The API uses keyset pagination. To load the next page, pass the `next_cursor` from the previous response:

```http
GET /games?search=elden&genre=RPG&limit=20&cursor_value=550000&cursor_id=1245620
```

Keep the same `sort`, `order`, and filter parameters between cursor requests. If `next_cursor` is `null`, there is no next page.

### Count And Distribution

Use expensive calculations only when the UI needs them:

```http
GET /games?genre=RPG&include_total=true&include_distribution=true
```

When enabled:

```json
{
  "total_count": 238,
  "genre_distribution": [
    {"label": "RPG", "count": 238}
  ],
  "positive_ratio_distribution": [
    {"label": "90-100", "count": 42},
    {"label": "80-89", "count": 91}
  ]
}
```

Recommended frontend usage:

- Search typing and infinite scroll: `include_total=false&include_distribution=false`
- Filter sidebar charts: `include_distribution=true`
- Showing exact result count: `include_total=true`

## Genres

```http
GET /genres
```

Returns genre dropdown options. This endpoint is cached in memory for 5 minutes.

```json
[
  {"genre": "Action", "game_count": 1200},
  {"genre": "RPG", "game_count": 238}
]
```

## Dashboard Summary

```http
GET /dashboard/summary
GET /dashboard/summary?start_date=2026-01-01&end_date=2026-01-31
```

Returns total games, reviews, average positive ratio, top genre, and optional previous-period changes.

## Trends

```http
GET /analysis/trends
```

Returns monthly market review/sentiment trend plus top genre trend series. Without date filters, the market trend reads from `mv_monthly_market_trends`.

## Price Review Scatter

```http
GET /analysis/price-review?limit=1000
```

Returns price, total reviews, and positive ratio for bubble/scatter charts. Reads from `mv_price_review_points`.

## Aggregate Analysis

These endpoints are intended for dashboard charts so the frontend does not need to fetch every game and aggregate locally.

```http
GET /analysis/genre-stats
```

Returns average price, average review count, average positive ratio, and game count by genre.

```json
{
  "items": [
    {
      "genre": "Action",
      "game_count": 120,
      "avg_price": 18500,
      "avg_review_count": 3400,
      "avg_positive_ratio": 78.4
    }
  ]
}
```

```http
GET /analysis/price-band-stats
```

Returns fixed server-side price buckets: `Free`, `0-5000`, `5000-15000`, `15000-30000`, `30000+`.

```http
GET /analysis/platform-stats
```

Returns Windows, Mac, and Linux support counts with average positive ratio.

## Game History

```http
GET /games/{game_id}/history?interval=day
GET /games/{game_id}/history?interval=month&start_date=2026-01-01&end_date=2026-05-01
```

Returns review count, positive ratio, player stats, and price history points. Price data comes from `game_price_history`.

## Wishlist

This project does not implement login, registration, JWT, or a `users` table. Wishlist and notifications remain demo-friendly and use `X-Client-Id` to separate browser/client instances.

Frontend recommendation:

1. Generate a stable `client_id` once.
2. Store it in `localStorage`.
3. Send it on wishlist/notification requests.

```http
X-Client-Id: browser-generated-client-id
```

```http
GET /users/me/wishlist
POST /users/me/wishlist
DELETE /users/me/wishlist/{game_id}
GET /users/me/wishlist/compare
```

POST body:

```json
{
  "game_id": 1245620
}
```

## Notifications

```http
GET /users/me/notifications
```

Also scoped by `X-Client-Id`.

For a real multi-user production service, this can later be replaced with JWT authentication. That is intentionally out of scope for the current project.

## Operational Commands

Initialize schema and indexes:

```powershell
python database\db_setup_v2.py
```

Refresh materialized views after collection/analysis:

```powershell
python database\refresh_materialized_views.py
```

Run backend:

```powershell
uvicorn backend.main:app --reload
```

Verify against a real DB and running API:

```powershell
python scripts\verify_api_real_db.py --base-url <provided-api-origin>
```

Or:

```powershell
$env:API_BASE_URL="<provided-api-origin>"
python scripts\verify_api_real_db.py
```
