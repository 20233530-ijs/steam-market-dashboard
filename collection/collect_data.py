import requests
import json
import csv
from datetime import datetime

# SteamSpy API
url = "https://steamspy.com/api.php?request=top100in2weeks"

print("Steam 인기 게임 데이터 수집 중...")

response = requests.get(url)
data = response.json()

# CSV 파일로 저장
filename = f"steam_games_{datetime.now().strftime('%Y%m%d')}.csv"

with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    
    # 헤더(컬럼명) 작성
    writer.writerow(['app_id', 'name', 'owners', 'positive', 'negative', 'average_playtime', 'price'])
    
    # 데이터 작성
    for app_id, game in data.items():
        writer.writerow([
            app_id,
            game['name'],
            game['owners'],
            game['positive'],
            game['negative'],
            game['average_forever'],
            game['price']
        ])

print(f"저장 완료! 파일명: {filename}")
print(f"총 {len(data)}개 게임 저장됨")