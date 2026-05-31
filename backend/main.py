import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import analysis, games, sentiment, topics


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")

app = FastAPI(
    title="Steam Market Dashboard API",
    description=(
        "FastAPI backend for Steam market, review sentiment, topic, "
        "and correlation analysis results."
    ),
    version="1.0.0",
)

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5500",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:8080",
    "null",
]


def get_allowed_origins() -> list[str]:
    env_origins = os.getenv("BACKEND_CORS_ORIGINS", "")
    configured_origins = [origin.strip() for origin in env_origins.split(",") if origin.strip()]
    if configured_origins:
        return sorted(set(configured_origins))
    return DEFAULT_CORS_ORIGINS


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check() -> dict:
    return {"status": "ok", "message": "Steam Market Dashboard API is running"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(games.router)
app.include_router(games.catalog_router)
app.include_router(games.users_router)
app.include_router(sentiment.router)
app.include_router(topics.router)
app.include_router(analysis.router)
