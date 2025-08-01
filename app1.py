import streamlit as st
import pandas as pd
import requests
import time
import folium
from streamlit_folium import st_folium
from dotenv import load_dotenv
import os
import re

"""
This application provides restaurant recommendations near a user‑selected tourist
attraction. It uses the Google Places and Geocoding APIs to search for
attractions and restaurants, then displays the results in a table and on a
folium map.  A new feature has been added so that immediately below the
application's title the top four tourist attractions are highlighted based on
their star ratings.  These recommendations are derived from the search
results and give users a quick summary of the highest‑rated places in their
area of interest.

The existing functions and logic are preserved exactly as provided by the
user.  Only additional code has been appended where necessary to compute and
display the top four attractions.  This ensures that the core behavior of
searching, selecting a place, and listing nearby restaurants remains
unchanged.
"""

load_dotenv()
api_key = os.getenv("Google_key")

def preprocess_restaurant_data(df):
    # 이름 전처리
    df['이름'] = df['이름'].astype(str).str.strip()
    df = df[~df['이름'].isin(['-', '없음', '', None])]
    df = df.drop_duplicates(subset='이름')

    # 평점 전처리
    df['평점'] = pd.to_numeric(df['평점'], errors='coerce')
    df = df.dropna(subset=['평점'])

    # 주소 전처리
    df['주소'] = df['주소'].astype(str).str.strip()
    df['주소'] = df['주소'].str.replace(r'^KR, ?', '', regex=True)
    df['주소'] = df['주소'].str.replace(r'^South Korea,?\s*', '', regex=True)
    df['주소'] = df['주소'].str.rstrip('/')

    # 영어 주소 제거
    df = df[~df['주소'].apply(lambda x: bool(re.fullmatch(r'[A-Za-z0-9 ,.-]+', x)))]

    df = df[df['주소'].str.strip() != '']
    df = df.dropna(subset=['주소'])

    # 정렬
    df = df.sort_values(by='평점', ascending=False)

    return df.reset_index(drop=True)

def get_lat_lng(address, api_key):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {'address': address, 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    if res['status'] == 'OK':
        location = res['results'][0]['geometry']['location']
        return location['lat'], location['lng']
    return None, None

# 3km로 잡긴 했는데 조금 근처에 잡고 싶어서 2km로 했습니다.
def find_nearby_restaurants(lat, lng, api_key, radius=2000):
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

def search_places(query, api_key):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {'query': f"{query} 관광지", 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    return res.get('results', [])

def get_place_photo_url(photo_reference: str, api_key: str, maxwidth: int = 400) -> str:
    """Construct a URL for retrieving a place photo from the Google Places API.

    The Places Photo endpoint requires a photo reference, a maximum width or
    height, and an API key.  This helper returns a URL that can be passed
    directly to ``st.image`` for display.  See the Google Places API docs
    for details: https://developers.google.com/maps/documentation/places/web-service/photos

    Parameters
    ----------
    photo_reference : str
        The photo reference string provided in the place search results.
    api_key : str
        Your Google API key.
    maxwidth : int, optional
        The maximum desired width of the image in pixels.  Defaults to 400.

    Returns
    -------
    str
        A URL to the photo endpoint that will return the image when requested.
    """
    return (
        f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={maxwidth}"  # noqa: E501
        f"&photoreference={photo_reference}&key={api_key}"
    )


def display_top_attractions(places):
    """Display the top four tourist attractions based on rating, with photos.

    Parameters
    ----------
    places : list of dict
        A list of place dictionaries as returned by the Google Places
        TextSearch API.  Each dictionary may contain 'name', 'rating', and
        optionally a 'photos' list with a ``photo_reference``.

    This function sorts the provided list of places by their star ratings in
    descending order and displays the top four as a row of columns.  Only
    attractions with a valid numerical rating are considered.  Each entry
    shows the name, rating, and a representative image (when available).
    If fewer than four attractions have ratings, the list will be shortened
    accordingly.
    """
    # Filter out places without a numeric rating
    rated_places = [p for p in places if isinstance(p.get('rating'), (int, float))]
    rated_places = sorted(rated_places, key=lambda p: p['rating'], reverse=True)
    top_four = rated_places[:4]
    if not top_four:
        return

    st.markdown("#### ⭐ 추천 관광지 Top 4")
    # Create columns equal to the number of recommendations (up to 4)
    cols = st.columns(len(top_four))
    for idx, place in enumerate(top_four):
        with cols[idx]:
            st.markdown(f"**{place['name']}**")
            st.markdown(f"평점: {place['rating']}")
            # Attempt to display a representative image for the place
            photos = place.get('photos')
            if photos:
                # Use the first photo reference provided by the API
                photo_ref = photos[0].get('photo_reference')
                if photo_ref:
                    photo_url = get_place_photo_url(photo_ref, api_key, maxwidth=400)
                    # Display the image. Streamlit will fetch it lazily when rendering.
                    st.image(photo_url, caption=place['name'], use_column_width=True)

def main():
    st.set_page_config(page_title="관광지 주변 맛집 추천", layout="wide")
    st.title("📍 관광지 주변 맛집 추천 시스템")

    if not api_key:
        st.error("❗ .env 파일에 'Google_key'가 설정되지 않았습니다.")
        return

    # 입력창과 초기화
    query = st.text_input("가고 싶은 지역을 입력하세요", "제주")

    if "places" not in st.session_state:
        st.session_state.places = None
    if "selected_place" not in st.session_state:
        st.session_state.selected_place = None

    # When the user clicks the search button, perform a text search and store results
    if st.button("관광지 검색"):
        st.session_state.places = search_places(query, api_key)
        st.session_state.selected_place = None  # Reset selection on new search

    # If there are search results, display the top four attractions immediately below the title
    if st.session_state.places:
        display_top_attractions(st.session_state.places)

        # Provide a dropdown for the user to choose a specific attraction
        place_names = [p['name'] for p in st.session_state.places]
        selected = st.selectbox("관광지를 선택하세요", place_names)

        # Update session state if the user changes their selection
        if st.session_state.selected_place != selected:
            st.session_state.selected_place = selected

        # Retrieve detailed information about the selected place
        selected_place = next(p for p in st.session_state.places if p['name'] == st.session_state.selected_place)
        address = selected_place.get('formatted_address')
        rating = selected_place.get('rating', '없음')

        st.markdown(f"### 🏞 관광지: {st.session_state.selected_place}")
        st.write(f"📍 주소: {address}")
        st.write(f"⭐ 평점: {rating}")

        # Geocode the selected address and handle any failures
        lat, lng = get_lat_lng(address, api_key)
        if lat is None:
            st.error("위치 정보를 불러오지 못했습니다.")
            return

        st.subheader("🍽 주변 3km 맛집 Top 10")

        # Find nearby restaurants and display them in a table
        restaurants = find_nearby_restaurants(lat, lng, api_key)
        df = pd.DataFrame(restaurants)
        df = preprocess_restaurant_data(df)
        st.dataframe(df[['이름', '주소', '평점']].head(10))

        # Show the attractions and restaurants on a map
        st.subheader("🗺 지도에서 보기")
        m = folium.Map(location=[lat, lng], zoom_start=13)
        folium.Marker([lat, lng], tooltip="관광지", icon=folium.Icon(color="blue")).add_to(m)
        for _, r in df.iterrows():
            folium.Marker(
                [r['위도'], r['경도']],
                tooltip=f"{r['이름']} (⭐{r['평점']})",
                icon=folium.Icon(color="green", icon="cutlery", prefix='fa')
            ).add_to(m)
        st_folium(m, width=700, height=500)

        # Provide CSV download of restaurant list
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 맛집 목록 CSV 다운로드",
            data=csv,
            file_name=f"{selected}_맛집목록.csv",
            mime='text/csv'
        )

if __name__ == "__main__":
    main()