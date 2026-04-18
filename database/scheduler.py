import os
import signal
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

API_KEY = os.getenv("API_KEY")
DB_PASSWORD = os.getenv("DB_PASSWORD")

scheduler = BlockingScheduler()


def shutdown_scheduler(signum=None, frame=None):
    print(f"종료 신호 수신: {datetime.now()}")

    if scheduler.running:
        scheduler.shutdown(wait=False)

    sys.exit(0)


def collect_data():
    print(f"데이터 수집 시작: {datetime.now()}")

    conn = None
    cursor = None

    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="postgres",
            user="postgres",
            password=DB_PASSWORD,
            connect_timeout=10,
        )
        cursor = conn.cursor()

        # 외부 API 응답 지연 시 Ctrl+C 종료가 지나치게 늦어지지 않도록 타임아웃을 둡니다.
        url = "https://steamspy.com/api.php?request=top100in2weeks"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        count = 0
        for app_id, game in data.items():
            try:
                cursor.execute(
                    """
                    INSERT INTO games (app_id, name, genre, price, tags)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (app_id) DO NOTHING
                    """,
                    (
                        int(app_id),
                        game["name"],
                        game.get("genre", ""),
                        game.get("price", 0),
                        str(game.get("tags", "")),
                    ),
                )

                cursor.execute(
                    """
                    INSERT INTO game_stats (app_id, owners, positive_reviews, negative_reviews, average_playtime)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        int(app_id),
                        game.get("owners", ""),
                        game.get("positive", 0),
                        game.get("negative", 0),
                        game.get("average_forever", 0),
                    ),
                )
                count += 1
            except Exception:
                conn.rollback()
                continue

        conn.commit()
        print(f"수집 완료: {count}개 게임 저장 ({datetime.now()})")

    except KeyboardInterrupt:
        print("데이터 수집 중 인터럽트가 감지되었습니다.")
        raise
    except Exception as e:
        print(f"에러 발생: {e}")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


scheduler.add_job(collect_data, "cron", hour=0, minute=0)

signal.signal(signal.SIGINT, shutdown_scheduler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, shutdown_scheduler)

print("스케줄러 시작! 매일 자정에 데이터를 자동 수집합니다.")
print("종료하려면 Ctrl+C 를 누르세요.")

try:
    collect_data()
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    shutdown_scheduler()
