import psycopg2
import matplotlib.pyplot as plt
import matplotlib
import seaborn as sns

# 한글 폰트 설정
matplotlib.rcParams['font.family'] = 'Malgun Gothic'
matplotlib.rcParams['axes.unicode_minus'] = False

# DB 연결
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="postgres",
    user="postgres",
    password="159357"
)
cursor = conn.cursor()

# 인기게임 TOP 10 가져오기
cursor.execute("""
    SELECT g.name, gs.positive_reviews
    FROM games g
    JOIN game_stats gs ON g.app_id = gs.app_id
    ORDER BY gs.positive_reviews DESC
    LIMIT 10
""")

rows = cursor.fetchall()
names = [row[0] for row in rows]
reviews = [row[1] for row in rows]

cursor.close()
conn.close()

# 시각화
plt.figure(figsize=(12, 6))
sns.barplot(x=reviews, y=names, palette='Blues_r')
plt.title('Steam 인기게임 TOP 10 (긍정 리뷰 기준)')
plt.xlabel('긍정 리뷰 수')
plt.ylabel('게임명')
plt.tight_layout()
plt.show()