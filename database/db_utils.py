import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"


def load_environment():
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)


def get_db_config():
    load_environment()
    missing = [
        name
        for name in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
        if not os.getenv(name)
    ]
    if missing:
        raise RuntimeError(f"Missing required database environment variables: {', '.join(missing)}")

    return {
        "host": os.getenv("DB_HOST"),
        "port": int(os.getenv("DB_PORT")),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }


def get_connection():
    return psycopg2.connect(**get_db_config())


def get_database_url():
    config = get_db_config()
    return URL.create(
        drivername="postgresql+psycopg2",
        username=config["user"],
        password=config["password"],
        host=config["host"],
        port=config["port"],
        database=config["database"],
    )


def get_engine():
    return create_engine(get_database_url())


def ensure_artifacts_dir():
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS_DIR
