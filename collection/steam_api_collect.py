import requests
import psycopg2

API_KEY = "KEY입력"

# 1. Steam Web API로 게임 목록 가져오기
print("Steam Web API 데이터 수집 중...")
url = f"https://api.steampowered.com/IStoreService/GetAppList/v1/?key={API_KEY}&include_games=1&limit=100"
response = requests.get(url)
apps = response.json()['response']['apps']
print(f"게임 목록 {len(apps)}개 가져옴")

# 2. DB 연결
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="postgres",
    user="postgres",
    password="SQL비밀번호"
)
cursor = conn.cursor()

# 3. 테이블 생성
cursor.execute("""
    CREATE TABLE IF NOT EXISTS steam_games (
        app_id INTEGER PRIMARY KEY,
        name VARCHAR(200)
    )
""")

# 4. 데이터 저장
count = 0
for app in apps:
    cursor.execute("""
        INSERT INTO steam_games (app_id, name)
        VALUES (%s, %s)
        ON CONFLICT (app_id) DO NOTHING
    """, (
        app['appid'],
        app['name']
    ))
    count += 1

conn.commit()
print(f"DB 저장 완료! {count}개 게임 저장됨")

cursor.close()
conn.close()