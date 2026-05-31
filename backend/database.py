import os
from pathlib import Path
from typing import Iterator

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")


def get_db_config() -> dict:
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


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(**get_db_config(), cursor_factory=RealDictCursor)


def get_db() -> Iterator[psycopg2.extensions.connection]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
