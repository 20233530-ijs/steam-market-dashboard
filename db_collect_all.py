import requests
import psycopg2

API_KEY = "KEY입력"

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="postgres",
    user="postgres",
    password="SQL비밀번호"
)
cursor = conn.cursor()

print("SteamSpy 데이터 수집 중...")

url = "https://steamspy.com/api.php?request=top100in2weeks"
response = requests.get(url)
data = response.json()

count = 0
for app_id, game in data.items():
    try:
        # games 테이블에 저장
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

        # game_stats 테이블에 저장
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
        print(f"에러: {e}")
        conn.rollback()
        continue

conn.commit()
print(f"완료! {count}개 게임 저장됨")

cursor.close()
conn.close()