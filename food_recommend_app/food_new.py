import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random

BASE_URL = "https://www.fatsecret.kr"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/115.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": BASE_URL
}

# 1️⃣ 음식 리스트 크롤링
def get_food_list(page=1):
    url = f"{BASE_URL}/칼로리-영양소/?page={page}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    data = []
    
    rows = soup.select("table.generic.food a.prominent")
    for row in rows:
        name = row.text.strip()
        link = BASE_URL + row["href"]
        data.append({"음식명": name, "링크": link})
    
    return data

# 2️⃣ 음식 상세 페이지 크롤링 (칼로리, 단백질, 탄수화물)
def get_food_details(url):
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        return None, None, None
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    try:
        # 칼로리
        cal = soup.select_one("div.nutrition_facts span.calorie").text.strip()
    except:
        cal = None
    
    # 영양성분 표에서 단백질과 탄수화물 추출
    protein, carbs = None, None
    rows = soup.select("table.nutrition_facts tr")
    for row in rows:
        label = row.select_one("td").text.strip() if row.select_one("td") else ""
        value = row.select_one("td + td").text.strip() if row.select_one("td + td") else ""
        
        if "단백질" in label:
            protein = value
        elif "탄수화물" in label:
            carbs = value
    
    return cal, protein, carbs

# 3️⃣ 전체 페이지 크롤링
all_foods = []
for page in range(1, 3):  # 테스트: 2페이지까지만
    food_list = get_food_list(page)
    
    for food in food_list:
        cal, protein, carbs = get_food_details(food["링크"])
        all_foods.append({
            "음식명": food["음식명"],
            "칼로리": cal,
            "단백질": protein,
            "탄수화물": carbs,
            "링크": food["링크"]
        })
        
        # 요청 간격 랜덤 딜레이
        time.sleep(random.uniform(1.5, 3.5))

df = pd.DataFrame(all_foods)
print(df.head())

# CSV 저장
df.to_csv("fatsecret_food_details.csv", index=False, encoding="utf-8-sig")
