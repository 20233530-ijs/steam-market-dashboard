# Steam Market Dashboard

Steam Market Dashboard collects Steam game market data, gathers recent reviews, runs text analysis, and exposes the results through a FastAPI backend and a lightweight browser dashboard.

## Project Layout

- `collection/`: quick Steam API and SteamSpy collection helpers.
- `database/`: PostgreSQL schema setup, official collection pipeline, review preprocessing, analysis, and chart generation.
- `backend/`: FastAPI app and API routers.
- `frontend/`: static dashboard that reads from the FastAPI API.
- `artifacts/`: generated CSV and PNG analysis outputs.

## Setup

Create a `.env` file in the project root:

```env
API_KEY=your_steam_web_api_key
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_postgres_password

```

Install Python dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m nltk.downloader vader_lexicon
```

## Data Pipeline

The official pipeline entrypoint is `database/run_analysis_pipeline.py`.

```powershell
python database\db_setup_v2.py
python database\run_analysis_pipeline.py --steam-web-api-limit 1000 --game-limit 500 --limit 100 --max-pages 5 --page-size 100 --workers 8
```

Pipeline order:

1. Seed app ids and names from Steam Web API.
2. Enrich market stats from SteamSpy. The default source is `request=all` with `--game-limit 500`.
3. Enrich official metadata from Steam Store appdetails.
4. Collect Steam Store reviews for stored games.
5. Clean and tokenize English reviews.
6. Run sentiment analysis, topic modeling, feature generation, and correlations.
7. Export CSV and PNG artifacts.
8. Serve the results through FastAPI.

Useful options:

```powershell
python database\run_analysis_pipeline.py --skip-game-collection --limit 5
python database\run_analysis_pipeline.py --steps collect-reviews preprocess analyze --skip-game-collection --limit 100 --workers 8
python database\run_analysis_pipeline.py --steps preprocess analyze --skip-game-collection --limit 100 --export-full
python database\run_analysis_pipeline.py --steps analyze --skip-game-collection --limit 100 --no-incremental
python database\run_analysis_pipeline.py --steam-web-api-limit 3000 --game-limit 2000 --limit 2000 --max-pages 10 --page-size 100 --min-reviews 200 --steps collect preprocess analyze --resume --export-full
python database\run_analysis_pipeline.py --game-limit 2500 --min-reviews 300 --steps analyze --resume
python collection\steam_api_collect.py --game-limit 1000 --max-results 1000
python collection\steam_store_details_collect.py --limit 500 --cc us
python database\run_analysis_pipeline.py --skip-visualizations --max-pages 1
python database\db_collect_all.py --request all --game-limit 1000
python database\scheduler.py
```

By default the pipeline runs incrementally: games that already have reviews are skipped during
review collection, reviews already present in `cleaned_reviews` are skipped during preprocessing,
and sentiment is calculated only for cleaned reviews missing from `review_sentiments`. Use
`--no-incremental` when you intentionally want to reprocess the selected dataset.

Data sources:

- Steam Web API: app ids and official names.
- SteamSpy API: genre, price, owner ranges, positive/negative review counts, average playtime, and tags.
- Steam Store appdetails API: genres, developers, publishers, release dates, supported languages, and official price details.
- Steam Store Reviews API: review text used for sentiment and topic analysis.

For stronger game-level correlation analysis, increase `--game-limit`. Correlation `sample_size`
is based on the number of games in `game_analysis_features`, not the number of reviews. Use
`--game-limit 1000` or higher when you want the backend reliability label to reach at least
the 1000-game threshold.

Use `--min-reviews` to exclude low-signal games before review collection and analysis. The filter
uses the latest SteamSpy positive plus negative review count and orders selected games by that same
review signal, so the pipeline prioritizes popular games with enough review volume for more reliable
sentiment, topic, and correlation analysis. The `--resume` flag keeps the default incremental skip
logic enabled for clearer long-running collection commands.

## Backend

Start the API:

```powershell
uvicorn backend.main:app --reload
```

Key endpoints:

- `GET /`
- `GET /health`
- `GET /games`
- `GET /games/{game_id}`
- `GET /games/{game_id}/sentiment`
- `GET /games/{game_id}/topics`
- `GET /analysis/correlation`
- `GET /dashboard/summary`

## Frontend

Serve the static dashboard from the project root:

```powershell
python -m http.server 5500 -d frontend
```

Open `http://localhost:5500` and keep the API URL set to `http://localhost:8000`.

## Tests

Run the smoke tests:

```powershell
python -m unittest discover -s tests
```
