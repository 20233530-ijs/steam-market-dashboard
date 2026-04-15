import requests

API_KEY = "KEY"

# 새로운 API 엔드포인트
url = f"https://api.steampowered.com/IStoreService/GetAppList/v1/?key={API_KEY}&include_games=1&limit=10"

print("Steam API 연결 테스트 중...")

response = requests.get(url)
print(f"상태코드: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    apps = data['response']['apps']
    print(f"연결 성공! 가져온 게임 수: {len(apps)}개")
    for app in apps[:5]:
        print(f"  {app['appid']} - {app['name']}")
else:
    print(response.text[:300])