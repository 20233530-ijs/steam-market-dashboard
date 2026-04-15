import psycopg2
import csv
import glob

# 가장 최근 CSV 파일 자동으로 찾기
csv_files = glob.glob("steam_games_*.csv")
filename = csv_files[0]
print(f"불러올 파일: {filename}")

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="postgres",
    user="postgres",
    password="SQL비밀번호"
)

cursor = conn.cursor()

with open(filename, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    count = 0
    for row in reader:
        cursor.execute("""
            INSERT INTO games (app_id, name, owners, positive, negative, average_playtime, price)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (app_id) DO NOTHING
        """, (
            row['app_id'],
            row['name'],
            row['owners'],
            row['positive'],
            row['negative'],
            row['average_playtime'],
            row['price']
        ))
        count += 1

conn.commit()
print(f"DB 저장 완료! {count}개 게임 저장됨")

cursor.close()
conn.close()