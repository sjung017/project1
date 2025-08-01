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
