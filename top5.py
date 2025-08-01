import streamlit as st
import pandas as pd
import requests
import time
import os
import re
import textwrap
import io
from PIL import Image
import streamlit.components.v1 as components
from dotenv import load_dotenv

# 환경변수에서 API 키를 읽습니다.
load_dotenv()
google_key = os.getenv("Google_key")
kakao_key = os.getenv("KAKAO_KEY")

# 맛집 데이터 전처리
def preprocess_restaurant_data(df: pd.DataFrame) -> pd.DataFrame:
    df['이름'] = df['이름'].astype(str).str.strip()
    df = df[~df['이름'].isin(['-', '없음', '', None])]
    df = df.drop_duplicates(subset='이름')

    df['평점'] = pd.to_numeric(df['평점'], errors='coerce')
    df = df.dropna(subset=['평점'])

    df['주소'] = df['주소'].astype(str).str.strip()
    df['주소'] = df['주소'].str.replace(r'^KR, ?', '', regex=True)
    df['주소'] = df['주소'].str.replace(r'^South Korea,?\s*', '', regex=True)
    df['주소'] = df['주소'].str.rstrip('/')

    df = df[~df['주소'].apply(lambda x: bool(re.fullmatch(r'[A-Za-z0-9 ,.-]+', x)))]
    df = df[df['주소'].str.strip() != '']
    df = df.dropna(subset=['주소'])

    df = df.sort_values(by='평점', ascending=False)
    return df.reset_index(drop=True)

# 주소 → 위경도 변환
def get_lat_lng(address: str, api_key: str):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {'address': address, 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    if res['status'] == 'OK':
        location = res['results'][0]['geometry']['location']
        return location['lat'], location['lng']
    return None, None

# 주변 맛집 검색
def find_nearby_restaurants(lat: float, lng: float, api_key: str, radius: int = 2000):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        'location': f'{lat},{lng}',
        'radius': radius,
        'type': 'restaurant',
        'language': 'ko',
        'key': api_key
    }
    res = requests.get(url, params=params).json()
    time.sleep(1)
    results = res.get('results', [])[:15]
    restaurants = []
    for r in results:
        restaurants.append({
            '이름': r.get('name'),
            '주소': r.get('vicinity'),
            '평점': r.get('rating', '없음'),
            '위도': r['geometry']['location']['lat'],
            '경도': r['geometry']['location']['lng']
        })
    return restaurants

# 관광지 검색
def search_places(query: str, api_key: str):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {'query': f"{query} 관광지", 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    return res.get('results', [])

# Google Places Photo API URL 생성
def get_place_photo_url(photo_reference: str, api_key: str, maxwidth: int = 400) -> str:
    return (
        f"https://maps.googleapis.com/maps/api/place/photo"
        f"?maxwidth={maxwidth}&photoreference={photo_reference}&key={api_key}"
    )

# 추천 관광지 5곳 표시 (이름, 평점, 사진, 주소)
def display_top_attractions(places: list):
    rated_places = [
        p for p in places if isinstance(p.get('rating'), (int, float))
    ]
    rated_places = sorted(rated_places, key=lambda p: p['rating'], reverse=True)
    top_five = rated_places[:5]
    if not top_five:
        return

    st.markdown("#### ⭐ 추천 관광지 Top 5")
    cols = st.columns(len(top_five))
    for idx, place in enumerate(top_five):
        with cols[idx]:
            # 이름과 평점
            st.markdown(f"**{place['name']}**")
            st.markdown(f"평점: {place['rating']}")

            # 사진: 300x200 크기로 통일
            photos = place.get('photos')
            if photos:
                ref = photos[0].get('photo_reference')
                if ref:
                    url = get_place_photo_url(ref, google_key)
                    try:
                        resp = requests.get(url)
                        img = Image.open(io.BytesIO(resp.content))
                        img = img.resize((300, 200))
                        st.image(img)
                    except Exception:
                        # 실패 시 URL 그대로 사용하되 너비만 지정
                        st.image(url, width=300)

            # 주소: '시' 또는 '도' 뒤에서 줄바꿈
            
            raw_address = place.get('formatted_address') or place.get('vicinity') or ''
            if '시' in raw_address:
                idx_si = raw_address.find('시')
                line1 = raw_address[:idx_si + 1]
                line2 = raw_address[idx_si + 1:].strip()
            elif '도' in raw_address:
                idx_do = raw_address.find('도')
                line1 = raw_address[:idx_do + 1]
                line2 = raw_address[idx_do + 1:].strip()
            else:
                parts = raw_address.split(' ', 1)
                line1 = parts[0] if parts else raw_address
                line2 = parts[1] if len(parts) > 1 else ''

            # 각 줄을 25자 이내로 줄이고 너무 길면 ... 처리
            line1 = textwrap.shorten(line1, width=25, placeholder='...')
            line2 = textwrap.shorten(line2, width=25, placeholder='...')

            # <br> 태그로 줄바꿈을 강제합니다.
            st.markdown(f"{line1}<br>{line2}", unsafe_allow_html=True)

# 메인 함수
def main():
    st.set_page_config(page_title="관광지 주변 맛집 추천", layout="wide")
    st.title("📍 관광지 주변 맛집 추천 시스템")

    if not google_key:
        st.error("❗ .env 파일에 'Google_key'가 설정되지 않았습니다.")
        return

    query = st.text_input("가고 싶은 지역을 입력하세요", "제주")

    if "places" not in st.session_state:
        st.session_state.places = None
    if "selected_place" not in st.session_state:
        st.session_state.selected_place = None

    if st.button("관광지 검색"):
        st.session_state.places = search_places(query, google_key)
        st.session_state.selected_place = None

    if st.session_state.places:
        # 추천 관광지 5곳 표시
        display_top_attractions(st.session_state.places)

        # 관광지 선택
        place_names = [p['name'] for p in st.session_state.places]
        selected = st.selectbox("관광지를 선택하세요", place_names)

        if st.session_state.selected_place != selected:
            st.session_state.selected_place = selected

        selected_place = next(
            p for p in st.session_state.places
            if p['name'] == st.session_state.selected_place
        )
        address = selected_place.get('formatted_address')
        rating = selected_place.get('rating', '없음')

        st.markdown(f"### 🏞 관광지: {st.session_state.selected_place}")
        st.write(f"📍 주소: {address}")
        st.write(f"⭐ 평점: {rating}")

        lat, lng = get_lat_lng(address, google_key)
        if lat is None:
            st.error("위치 정보를 불러오지 못했습니다.")
            return

        # 주변 맛집 목록
        st.subheader("🍽 주변 3km 맛집 Top 10")
        restaurants = find_nearby_restaurants(lat, lng, google_key)
        df = pd.DataFrame(restaurants)
        df = preprocess_restaurant_data(df)
        st.dataframe(df[['이름', '주소', '평점']].head(10))

        # KakaoMap으로 맛집 위치 표시
        st.subheader("🗺 지도에서 보기 (카카오맵)")
        places_js = ""
        for _, row in df.head(10).iterrows():
            places_js += f"""
                {{
                    name: "{row['이름']}",
                    address: "{row['주소']}",
                    lat: {row['위도']},
                    lng: {row['경도']}
                }},
            """

        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <script type="text/javascript"
              src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={kakao_key}&autoload=false&libraries=services">
            </script>
        </head>
        <body>
            <div id="map" style="width:100%; height:500px;"></div>
            <script>
              kakao.maps.load(function() {{
                var mapContainer = document.getElementById('map');
                var mapOption = {{
                  center: new kakao.maps.LatLng({lat}, {lng}),
                  level: 4
                }};
                var map = new kakao.maps.Map(mapContainer, mapOption);
                var places = [{places_js}];
                places.forEach(function(p) {{
                  var coords = new kakao.maps.LatLng(p.lat, p.lng);
                  var marker = new kakao.maps.Marker({{
                    map: map,
                    position: coords
                  }});
                  var infowindow = new kakao.maps.InfoWindow({{
                    content: "<div style='padding:5px; font-size:13px;'>" + p.name + "<br>" + p.address + "</div>"
                  }});
                  infowindow.open(map, marker);
                }});
              }});
            </script>
        </body>
        </html>
        """
        components.html(html_code, height=550)

        # CSV 다운로드 버튼
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 맛집 목록 CSV 다운로드",
            data=csv,
            file_name=f"{selected}_맛집목록.csv",
            mime='text/csv'
        )

if __name__ == "__main__":
    main()
