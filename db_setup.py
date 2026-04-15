import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="postgres",
    user="postgres",
    password="SQL비밀번호"
)

cursor = conn.cursor()

# 테이블 생성
cursor.execute("""
    CREATE TABLE IF NOT EXISTS games (
        app_id VARCHAR(20) PRIMARY KEY,
        name VARCHAR(200),
        owners VARCHAR(50),
        positive INTEGER,
        negative INTEGER,
        average_playtime INTEGER,
        price INTEGER
    )
""")

conn.commit()
print("테이블 생성 완료!")

cursor.close()
conn.close()