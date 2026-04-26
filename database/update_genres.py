import os
import requests
import time
from db_utils import get_connection, load_environment

load_environment()
API_KEY = os.getenv("API_KEY")

def get_genre_from_steam(app_id):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data and str(app_id) in data and data[str(app_id)]["success"]:
            genres = data[str(app_id)]["data"].get("genres", [])
            if genres:
                return genres[0]["description"]
    except Exception as e:
        print(f"에러 {app_id}: {e}")
    return None

def update_genres():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT app_id, name FROM games WHERE genre IS NULL OR genre = ''")
            games = cursor.fetchall()
        
        print(f"장르 업데이트 필요한 게임: {len(games)}개")
        
        updated = 0
        for app_id, name in games:
            genre = get_genre_from_steam(app_id)
            if genre:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE games SET genre = %s WHERE app_id = %s",
                        (genre, app_id)
                    )
                conn.commit()
                print(f"✅ {name}: {genre}")
                updated += 1
            else:
                print(f"❌ {name}: 장르 없음")
            time.sleep(0.5)  # API 요청 제한 방지
        
        print(f"\n완료! {updated}개 게임 장르 업데이트됨")

if __name__ == "__main__":
    update_genres()