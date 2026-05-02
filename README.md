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
python database\run_analysis_pipeline.py --limit 10 --max-pages 1 --page-size 50
```

Pipeline order:

1. Refresh SteamSpy top games and latest stats.
2. Collect Steam reviews for stored games.
3. Clean and tokenize English reviews.
4. Run sentiment analysis, topic modeling, feature generation, and correlations.
5. Export CSV and PNG artifacts.
6. Serve the results through FastAPI.

Useful options:

```powershell
python database\run_analysis_pipeline.py --skip-game-collection --limit 5
python database\run_analysis_pipeline.py --skip-visualizations --max-pages 1
python database\scheduler.py
```

## Backend

Start the API:

```powershell
uvicorn backend.main:app --reload
```

Key endpoints:

- `GET /`
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
