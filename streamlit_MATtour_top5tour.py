import streamlit as st
import pandas as pd
import requests
import time
import os
import re
import io
import textwrap
from PIL import Image
import streamlit.components.v1 as components
from dotenv import load_dotenv
import base64

# Load environment variables
load_dotenv()
google_key = os.getenv("Google_key")
kakao_key = os.getenv("KAKAO_KEY")

# -----------------------------------------------------------------------------
# 데이터 전처리 함수
# -----------------------------------------------------------------------------
def preprocess_restaurant_data(df: pd.DataFrame) -> pd.DataFrame:
 
    # Strip whitespace and remove placeholder names
    df['이름'] = df['이름'].astype(str).str.strip()
    df = df[~df['이름'].isin(['-', '없음', '', None])]
    # Remove duplicates based on the restaurant name
    df = df.drop_duplicates(subset='이름')
    # Convert ratings to numeric and drop rows without a rating
    df['평점'] = pd.to_numeric(df['평점'], errors='coerce')
    df = df.dropna(subset=['평점'])
    # Normalise the address
    df['주소'] = df['주소'].astype(str).str.strip()
    df['주소'] = df['주소'].str.replace(r'^KR, ?', '', regex=True)
    df['주소'] = df['주소'].str.replace(r'^South Korea,?\s*', '', regex=True)
    df['주소'] = df['주소'].str.rstrip('/')
    # Filter out addresses that are just english letters/numbers/punctuation
    df = df[~df['주소'].apply(lambda x: bool(re.fullmatch(r'[A-Za-z0-9 ,.-]+', x)))]
    df = df[df['주소'].str.strip() != '']
    df = df.dropna(subset=['주소'])
    # Sort by rating descending
    df = df.sort_values(by='평점', ascending=False)
    return df.reset_index(drop=True)


def get_lat_lng(address: str, api_key: str):

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {'address': address, 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    if res.get('status') == 'OK' and res['results']:
        location = res['results'][0]['geometry']['location']
        return location['lat'], location['lng']
    return None, None


def find_nearby_restaurants(lat: float, lng: float, api_key: str, radius: int = 3000):
 
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        'location': f'{lat},{lng}',
        'radius': radius,
        'type': 'restaurant',
        'language': 'ko',
        'key': api_key
    }
    res = requests.get(url, params=params).json()
    # Delay to avoid hitting rate limits
    time.sleep(1)
    results = res.get('results', [])
    # Filter out restaurants with fewer than 50 reviews
    results = [r for r in results if r.get('user_ratings_total', 0) >= 50]
    # Limit to the top 15 results to control API usage
    results = results[:15]
    restaurants = []
    for r in results:
        restaurants.append({
            '이름': r.get('name'),
            '주소': r.get('vicinity'),
            '평점': r.get('rating', '없음'),
            '위도': r['geometry']['location']['lat'],
            '경도': r['geometry']['location']['lng'],
            # Preserve photos and place_id for further use (e.g., images and reviews)
            'photos': r.get('photos'),
            'place_id': r.get('place_id'),
            # Also store number of reviews for potential future use
            'reviews_count': r.get('user_ratings_total', 0)
        })
    return restaurants


def search_places(query: str, api_key: str):

    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {'query': f"{query} 관광지", 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    results = res.get('results', [])
    # Filter places with at least 50 user ratings
    filtered = [p for p in results if p.get('user_ratings_total', 0) >= 50]
    return filtered


def get_place_photo_url(photo_reference: str, api_key: str, maxwidth: int = 400) -> str:

    return (
        f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={maxwidth}"
        f"&photoreference={photo_reference}&key={api_key}"
    )


def get_latest_review(place_id: str, api_key: str, language: str = 'ko'):
  
    details_url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        'place_id': place_id,
        'fields': 'review',
        'language': language,
        'key': api_key
    }
    try:
        res = requests.get(details_url, params=params).json()
        reviews = res.get('result', {}).get('reviews', [])
        if not reviews:
            return None
        # Sort reviews by timestamp descending to get the most recent
        latest = max(reviews, key=lambda x: x.get('time', 0))
        return latest
    except Exception:
        return None


def display_top_attractions(places: list):
   
    # Filter out places without numeric ratings and sort descending
    rated_places = [p for p in places if isinstance(p.get('rating'), (int, float))]
    rated_places = sorted(rated_places, key=lambda p: p['rating'], reverse=True)
    top_five = rated_places[:5]
    if not top_five:
        return
    st.markdown("#### ⭐ 추천 관광지 Top 5")
    cols = st.columns(len(top_five))
    for idx, place in enumerate(top_five):
        with cols[idx]:
            name = place.get('name', '')
            rating = place.get('rating', '없음')
            img_html = ''
            photos = place.get('photos')
            if photos:
                ref = photos[0].get('photo_reference')
                if ref:
                    url = get_place_photo_url(ref, google_key)
                    try:
                        resp = requests.get(url)
                        if resp.status_code == 200:
                            encoded = base64.b64encode(resp.content).decode()
                            # 고정 높이와 확대 효과를 적용한 이미지
                            img_html = (
                                f"<img src='data:image/jpeg;base64,{encoded}' "
                                "style='width:100%; height:150px; object-fit:cover; border-radius:8px; margin-top:5px; transition: transform 0.3s ease;' "
                                "onmouseover=\"this.style.transform='scale(1.05)'\" "
                                "onmouseout=\"this.style.transform='scale(1.0)'\"/>"
                            )
                        else:
                            # Fallback to serving via Google if direct fetch fails
                            img_html = (
                                f"<img src='{url}' "
                                "style='width:100%; height:150px; object-fit:cover; border-radius:8px; margin-top:5px; transition: transform 0.3s ease;' "
                                "onmouseover=\"this.style.transform='scale(1.05)'\" "
                                "onmouseout=\"this.style.transform='scale(1.0)'\"/>"
                            )
                    except Exception:
                        img_html = (
                            f"<img src='{url}' "
                            "style='width:100%; height:150px; object-fit:cover; border-radius:8px; margin-top:5px; transition: transform 0.3s ease;' "
                            "onmouseover=\"this.style.transform='scale(1.05)'\" "
                            "onmouseout=\"this.style.transform='scale(1.0)'\"/>"
                        )
            # Split address into two lines for neat display
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
            # Truncate lines to prevent overflow
            line1 = textwrap.shorten(line1, width=25, placeholder='…')
            line2 = textwrap.shorten(line2, width=25, placeholder='…')

            # Construct Google Maps link. Prefer place_id for accuracy.
            place_id = place.get('place_id')
            if place_id:
                place_link = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            else:
                query_name = requests.utils.quote(name)
                place_link = f"https://www.google.com/maps/search/?api=1&query={query_name}"

            # Fetch the latest review if available
            latest_review = None
            if place_id:
                latest_review = get_latest_review(place_id, google_key)
            if latest_review:
                review_text = latest_review.get('text', '')
                author_name = latest_review.get('author_name', '')
                review_snippet = textwrap.shorten(review_text, width=70, placeholder='…')
                review_html = (
                    f"<div style='margin-top:8px; height:auto; font-size:12px; line-height:1.4; color:#444444; text-align:center;'>“{review_snippet}”"
                    f"<br><span style='font-size:11px; color:#888888;'>- {author_name}</span></div>"
                )
            else:
                review_html = ''

            # Card HTML with fixed heights to align the review start position
            card_html = (
                "<div style=\"background-color:#F7F7F7; "
                "border-radius:15px; padding:16px; margin-top:10px; "
                "height:400px; display:flex; flex-direction:column; justify-content:flex-start; "
                "box-shadow:0 4px 8px rgba(0,0,0,0.1);\">"
                "<div style='display:flex; align-items:center; justify-content:space-between; min-height:36px;'>"
                f"<span style='font-weight:bold; font-size:18px; color:#000000; flex-grow:1; text-align:center;'>{name}</span>"
                f"<a href='{place_link}' target='_blank' style='font-size:14px; color:#999999; text-decoration:none; margin-left:4px;' "
                "onmouseover=\"this.style.color='#005FCC'\" onmouseout=\"this.style.color='#999999'\">🔗</a>"
                "</div>"
                f"{img_html}"
                f"<div style='margin-top:8px; min-height:28px; font-size:14px; color:#F39C12; text-align:center;'>⭐ {rating}</div>"
                f"<div style='margin-top:8px; min-height:44px; font-size:12px; line-height:1.4; color:#666666; text-align:center;'>{line1}<br>{line2}</div>"
                f"{review_html}"
                "</div>"
            )
            st.markdown(card_html, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 맛집 추천 카드 표시 함수
# -----------------------------------------------------------------------------
def display_top_restaurants(restaurants: pd.DataFrame):
 
    df = restaurants.copy()
    df['평점'] = pd.to_numeric(df['평점'], errors='coerce')
    df = df.dropna(subset=['평점'])
    if df.empty:
        return
    df = df.sort_values(by='평점', ascending=False).head(5)
    st.markdown("#### 🍽 추천 맛집 Top 5")
    cols = st.columns(len(df))
    for idx, row in df.reset_index(drop=True).iterrows():
        with cols[idx]:
            name = row['이름']
            rating = row['평점']
            img_html = ''
            photos = row.get('photos', None)
            if photos:
                ref = photos[0].get('photo_reference') if isinstance(photos, list) and photos else None
                if ref:
                    url = get_place_photo_url(ref, google_key)
                    try:
                        resp = requests.get(url)
                        if resp.status_code == 200:
                            encoded = base64.b64encode(resp.content).decode()
                            img_html = (
                                f"<img src='data:image/jpeg;base64,{encoded}' "
                                "style='width:100%; height:150px; object-fit:cover; border-radius:8px; margin-top:5px; transition: transform 0.3s ease;' "
                                "onmouseover=\"this.style.transform='scale(1.05)'\" "
                                "onmouseout=\"this.style.transform='scale(1.0)'\"/>"
                            )
                        else:
                            img_html = (
                                f"<img src='{url}' "
                                "style='width:100%; height:150px; object-fit:cover; border-radius:8px; margin-top:5px; transition: transform 0.3s ease;' "
                                "onmouseover=\"this.style.transform='scale(1.05)'\" "
                                "onmouseout=\"this.style.transform='scale(1.0)'\"/>"
                            )
                    except Exception:
                        img_html = (
                            f"<img src='{url}' "
                            "style='width:100%; height:150px; object-fit:cover; border-radius:8px; margin-top:5px; transition: transform 0.3s ease;' "
                            "onmouseover=\"this.style.transform='scale(1.05)'\" "
                            "onmouseout=\"this.style.transform='scale(1.0)'\"/>"
                        )
            raw_address = row['주소'] or ''
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
            line1 = textwrap.shorten(str(line1), width=25, placeholder='…')
            line2 = textwrap.shorten(str(line2), width=25, placeholder='…')
            place_id = row.get('place_id')
            if place_id:
                place_link = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            else:
                query_name = requests.utils.quote(name)
                place_link = f"https://www.google.com/maps/search/?api=1&query={query_name}"
            latest_review = None
            if place_id:
                latest_review = get_latest_review(place_id, google_key)
            if latest_review:
                review_text = latest_review.get('text', '')
                author_name = latest_review.get('author_name', '')
                review_snippet = textwrap.shorten(review_text, width=70, placeholder='…')
                review_html = (
                    f"<div style='margin-top:8px; height:auto; font-size:12px; line-height:1.4; color:#444444; text-align:center;'>“{review_snippet}”"
                    f"<br><span style='font-size:11px; color:#888888;'>- {author_name}</span></div>"
                )
            else:
                review_html = ''
            card_html = (
                "<div style=\"background-color:#F7F7F7; "
                "border-radius:15px; padding:16px; margin-top:10px; "
                "height:410px; display:flex; flex-direction:column; justify-content:flex-start; "
                "box-shadow:0 4px 8px rgba(0,0,0,0.1);\">"
                "<div style='display:flex; align-items:center; justify-content:space-between; height:48px; overflow:hidden; margin-bottom:5px;'>"
                f"<span style='font-weight:bold; font-size:18px; color:#000000; flex-grow:1; text-align:center;'>{name}</span>"
                f"<a href='{place_link}' target='_blank' style='font-size:14px; color:#999999; text-decoration:none; margin-left:4px;' "
                "onmouseover=\"this.style.color='#005FCC'\" onmouseout=\"this.style.color='#999999'\">🔗</a>"
                "</div>"
                f"{img_html}"
                f"<div style='margin-top:8px; min-height:28px; font-size:14px; color:#F39C12; text-align:center;'>⭐ {rating}</div>"
                f"<div style='margin-top:8px; min-height:44px; font-size:12px; line-height:1.4; color:#666666; text-align:center;'>{line1}<br>{line2}</div>"
                f"{review_html}"
                "</div>"
            )
            st.markdown(card_html, unsafe_allow_html=True)

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
        display_top_attractions(st.session_state.places)
        place_names = [p['name'] for p in st.session_state.places]
        selected = st.selectbox("관광지를 선택하세요", place_names)
        if st.session_state.selected_place != selected:
            st.session_state.selected_place = selected
        selected_place = next(
            (p for p in st.session_state.places if p['name'] == st.session_state.selected_place),
            None
        )
        if selected_place is None:
            st.warning("선택한 관광지를 찾을 수 없습니다.")
            return
        address = selected_place.get('formatted_address')
        rating = selected_place.get('rating', '없음')
        st.markdown(f"### 🏞 관광지: {st.session_state.selected_place}")
        st.write(f"📍 주소: {address}")
        st.write(f"⭐ 평점: {rating}")
        lat, lng = get_lat_lng(address, google_key)
        if lat is None:
            st.error("위치 정보를 불러오지 못했습니다.")
            return
        restaurants = find_nearby_restaurants(lat, lng, google_key)
        df = pd.DataFrame(restaurants)
        df = preprocess_restaurant_data(df)
        display_top_restaurants(df)
        st.subheader("🍽 주변 3km 맛집 Top 10")
        st.dataframe(df[['이름', '주소', '평점']].head(10))
        st.subheader("🗺 지도에서 보기 (카카오맵)")
        places_js = ""
        for _, row in df.head(10).iterrows():
            places_js += (
                "{"
                f"name: \"{row['이름']}\"," 
                f"address: \"{row['주소']}\"," 
                f"lat: {row['위도']}," 
                f"lng: {row['경도']}" 
                "},"
            )
        html_code = (
            "<!DOCTYPE html>"
            "<html>"
            "<head>"
            "<meta charset='utf-8'>"
            f"<script type='text/javascript' src='//dapi.kakao.com/v2/maps/sdk.js?appkey={kakao_key}'></script>"
            "</head>"
            "<body>"
            "<div id='map' style='width:100%; height:500px;'></div>"
            "<script>"
            f"var mapContainer = document.getElementById('map');"
            f"var mapOption = {{ center: new kakao.maps.LatLng({lat}, {lng}), level: 4 }};"
            "var map = new kakao.maps.Map(mapContainer, mapOption);"
            f"var places = [{places_js}];"
            "places.forEach(function(p) {"
            "var coords = new kakao.maps.LatLng(p.lat, p.lng);"
            "var marker = new kakao.maps.Marker({ map: map, position: coords });"
            "var infowindow = new kakao.maps.InfoWindow({ content: \"<div style='padding:5px; font-size:13px;'>\" + p.name + \"<br>\" + p.address + \"</div>\" });"
            "infowindow.open(map, marker);"
            "});"
            "</script>"
            "</body>"
            "</html>"
        )
        components.html(html_code, height=550)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📅 맛집 목록 CSV 다운로드",
            data=csv,
            file_name=f"{selected}_맛집목록.csv",
            mime='text/csv'
        )

if __name__ == "__main__":
    main()
