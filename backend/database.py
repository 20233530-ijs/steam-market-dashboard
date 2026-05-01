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
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "postgres"),
        "user": os.getenv("DB_USER", "postgres"),
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
