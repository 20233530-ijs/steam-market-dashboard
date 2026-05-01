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
    description="Steam 게임 시장 트렌드 분석 결과를 제공하는 FastAPI 백엔드",
    version="1.0.0",
)


def get_allowed_origins() -> list[str]:
    origins = os.getenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    )
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check() -> dict:
    return {"status": "ok", "message": "Steam Market Dashboard API is running"}


app.include_router(games.router)
app.include_router(sentiment.router)
app.include_router(topics.router)
app.include_router(analysis.router)
