import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="postgres",
        user="postgres",
        password="SQL비밀번호"
    )
    print("DB 연결 성공!")
    conn.close()

except Exception as e:
    print(f"연결 실패: {e}")