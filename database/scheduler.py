import requests
import psycopg2
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime

API_KEY = "KEY입력"
DB_PASSWORD = "SQL비밀번호"

def collect_data():
    print(f"데이터 수집 시작: {datetime.now()}")
    
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="postgres",
            user="postgres",
            password=DB_PASSWORD
        )
        cursor = conn.cursor()

        # SteamSpy 데이터 수집
        url = "https://steamspy.com/api.php?request=top100in2weeks"
        response = requests.get(url)
        data = response.json()

        count = 0
        for app_id, game in data.items():
            try:
                cursor.execute("""
                    INSERT INTO games (app_id, name, genre, price, tags)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (app_id) DO NOTHING
                """, (
                    int(app_id),
                    game['name'],
                    game.get('genre', ''),
                    game.get('price', 0),
                    str(game.get('tags', ''))
                ))

                cursor.execute("""
                    INSERT INTO game_stats (app_id, owners, positive_reviews, negative_reviews, average_playtime)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    int(app_id),
                    game.get('owners', ''),
                    game.get('positive', 0),
                    game.get('negative', 0),
                    game.get('average_forever', 0)
                ))
                count += 1

            except Exception as e:
                conn.rollback()
                continue

        conn.commit()
        print(f"수집 완료: {count}개 게임 저장됨 ({datetime.now()})")
        
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"에러 발생: {e}")

# 스케줄러 설정
scheduler = BlockingScheduler()

# 매일 자정에 실행
scheduler.add_job(collect_data, 'cron', hour=0, minute=0)

print("스케줄러 시작! 매일 자정에 데이터 자동 수집됩니다.")
print("종료하려면 Ctrl+C 누르세요.")

# 시작하자마자 한 번 실행
collect_data()

scheduler.start()