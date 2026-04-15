import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="postgres",
    user="postgres",
    password="SQL비밀번호"
)

cursor = conn.cursor()

# 기존 테이블 삭제 후 새로 만들기
cursor.execute("DROP TABLE IF EXISTS reviews")
cursor.execute("DROP TABLE IF EXISTS games")
cursor.execute("DROP TABLE IF EXISTS steam_games")

# 1. 게임 기본 정보 테이블
cursor.execute("""
    CREATE TABLE IF NOT EXISTS games (
        app_id INTEGER PRIMARY KEY,
        name VARCHAR(200),
        genre VARCHAR(100),
        price INTEGER,
        release_date VARCHAR(50),
        developer VARCHAR(200),
        publisher VARCHAR(200),
        languages TEXT,
        tags TEXT
    )
""")

# 2. 게임 통계 테이블 (흥행 지표)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS game_stats (
        stat_id SERIAL PRIMARY KEY,
        app_id INTEGER REFERENCES games(app_id),
        owners VARCHAR(50),
        positive_reviews INTEGER,
        negative_reviews INTEGER,
        average_playtime INTEGER,
        peak_players INTEGER,
        collected_at TIMESTAMP DEFAULT NOW()
    )
""")

# 3. 리뷰 테이블 (텍스트 마이닝용)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        review_id SERIAL PRIMARY KEY,
        app_id INTEGER REFERENCES games(app_id),
        review_text TEXT,
        voted_up BOOLEAN,
        playtime_hours INTEGER,
        collected_at TIMESTAMP DEFAULT NOW()
    )
""")

conn.commit()
print("테이블 3개 생성 완료!")
print("- games: 게임 기본 정보")
print("- game_stats: 흥행 지표")
print("- reviews: 리뷰 텍스트")

cursor.close()
conn.close()