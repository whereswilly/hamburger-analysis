import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from io import BytesIO

st.set_page_config(
    page_title='샤브올데이 경쟁점 반경 분석',
    page_icon='🍲',
    layout='wide'
)

# ── Session state defaults ────────────────────────────────────────────────────

for key, default in [('map_center', None), ('map_zoom', 7), ('selected_store', None)]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Utilities ─────────────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2_arr, lon2_arr):
    R = 6371.0
    rlat1, rlon1 = np.radians(lat1), np.radians(lon1)
    rlat2 = np.radians(np.asarray(lat2_arr, dtype=float))
    rlon2 = np.radians(np.asarray(lon2_arr, dtype=float))
    a = np.sin((rlat2 - rlat1) / 2)**2 + np.cos(rlat1) * np.cos(rlat2) * np.sin((rlon2 - rlon1) / 2)**2
    return 2 * R * np.arcsin(np.sqrt(a))

@st.cache_data
def load_data():
    allday = pd.read_excel('Competitors/샤브올데이_정리.xlsx').dropna(subset=['위도', '경도'])

    shabu20 = pd.read_excel('Competitors/샤브20_정리.xlsx')
    shabu20['브랜드'] = '샤브20'

    ashley = pd.read_excel('Competitors/애슐리_정리.xlsx')
    ashley['브랜드'] = '애슐리'

    cookcook = pd.read_excel('Competitors/쿠우쿠우.xlsx')
    cookcook['브랜드'] = '쿠우쿠우'

    competitors = pd.concat([
        shabu20[['브랜드', '매장명', '주소', '위도', '경도']],
        ashley[['브랜드', '매장명', '주소', '위도', '경도']],
        cookcook[['브랜드', '매장명', '주소', '위도', '경도']],
    ], ignore_index=True).dropna(subset=['위도', '경도'])

    return allday, competitors

@st.cache_data
def compute_analysis(radius_km: float, brands: tuple):
    allday, all_comps = load_data()
    active = all_comps[all_comps['브랜드'].isin(brands)].reset_index(drop=True)

    rows = []
    for _, store in allday.iterrows():
        row = {
            '매장명': store['매장명'],
            '주소':   store['주소'],
            '위도':   store['위도'],
            '경도':   store['경도'],
        }
        nearby_list = []

        if len(active) > 0:
            dists = haversine(store['위도'], store['경도'], active['위도'].values, active['경도'].values)
            mask = dists <= radius_km
            nearby = active[mask].copy()
            nearby['거리_km'] = dists[mask]
            nearby = nearby.sort_values('거리_km')
            nearby_list = list(zip(nearby['브랜드'], nearby['매장명'], nearby['거리_km']))

        total = 0
        for brand in brands:
            cnt = sum(1 for b, _, _ in nearby_list if b == brand)
            row[brand] = cnt
            total += cnt
        row['총계'] = total
        row['_nearby'] = nearby_list
        rows.append(row)

    return pd.DataFrame(rows)

# ── Map ───────────────────────────────────────────────────────────────────────

BRAND_COLORS = {
    '샤브20':   ('#1565C0', 'blue'),
    '애슐리':   ('#2E7D32', 'green'),
    '쿠우쿠우': ('#6A1B9A', 'purple'),
}

def build_map(result_df, active_comps, radius_km, brands, center, zoom):
    m = folium.Map(location=center, zoom_start=zoom, tiles='cartodbpositron')

    for brand in brands:
        bc = active_comps[active_comps['브랜드'] == brand]
        hex_color, _ = BRAND_COLORS.get(brand, ('#999', 'gray'))
        for _, comp in bc.iterrows():
            folium.CircleMarker(
                location=[comp['위도'], comp['경도']],
                radius=5, color=hex_color, fill_color=hex_color,
                fill=True, fill_opacity=0.75, weight=1,
                popup=folium.Popup(
                    f"<b>[{brand}]</b> {comp['매장명']}<br><small>{comp['주소']}</small>",
                    max_width=220
                )
            ).add_to(m)

    selected_name = st.session_state.selected_store
    for _, store in result_df.iterrows():
        nearby = store['_nearby']
        is_selected = (store['매장명'] == selected_name)

        brand_rows = ''.join(
            f'<tr><td style="padding:2px 8px">{b}</td>'
            f'<td style="padding:2px 8px" align="right"><b>{store.get(b, 0)}</b>개</td></tr>'
            for b in brands
        )
        nearby_items = ''.join(
            f'<li><span style="color:{BRAND_COLORS.get(b, ("#999",""))[0]}">[{b}]</span> '
            f'{n} <span style="color:#888">({d:.1f}km)</span></li>'
            for b, n, d in nearby
        ) or '<li>없음</li>'

        popup_html = (
            f'<div style="font-family:sans-serif;font-size:13px;width:280px;max-height:380px;overflow-y:auto">'
            f'<b style="font-size:15px;color:#C62828">{store["매장명"]}</b><br>'
            f'<small style="color:#666">{store["주소"]}</small>'
            f'<hr style="margin:6px 0">'
            f'<b>반경 {radius_km}km 이내 요약</b>'
            f'<table style="width:100%;border-collapse:collapse">{brand_rows}'
            f'<tr style="border-top:1px solid #ddd">'
            f'<td style="padding:2px 8px"><b>총계</b></td>'
            f'<td style="padding:2px 8px" align="right"><b>{store["총계"]}</b>개</td>'
            f'</tr></table>'
            f'<hr style="margin:6px 0"><b>상세 목록</b>'
            f'<ul style="margin:4px 0;padding-left:18px;line-height:1.6">{nearby_items}</ul>'
            f'</div>'
        )

        folium.Marker(
            location=[store['위도'], store['경도']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"★ {store['매장명']}  (경쟁점 {store['총계']}개)",
            icon=folium.Icon(color='darkred' if is_selected else 'red', icon='star', prefix='glyphicon')
        ).add_to(m)

        folium.Circle(
            [store['위도'], store['경도']], radius=radius_km * 1000,
            color='#E53935', fill=True,
            fill_opacity=0.12 if is_selected else 0.05, weight=1.5
        ).add_to(m)

    items = ['<span style="color:#E53935">★</span> 샤브올데이'] + [
        f'<span style="color:{BRAND_COLORS[b][0]}">●</span> {b}' for b in brands
    ] + [f'<span style="color:#E53935">○</span> 반경 {radius_km}km']
    legend_html = (
        '<div style="position:fixed;bottom:30px;right:10px;z-index:1000;background:white;'
        'padding:10px 16px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);'
        'font-size:13px;line-height:1.8">'
        '<b>범례</b><br>' + '<br>'.join(items) + '</div>'
    )
    m.get_root().html.add_child(folium.Element(legend_html))
    return m

# ── UI ────────────────────────────────────────────────────────────────────────

st.title('샤브올데이 경쟁점 반경 분석')

with st.sidebar:
    st.header('분석 설정')
    radius_km = st.slider('반경 (km)', min_value=0.5, max_value=10.0, value=3.0, step=0.5)
    st.markdown('---')
    st.markdown('**포함 브랜드**')
    show_s20 = st.checkbox('샤브20', value=True)
    show_ash = st.checkbox('애슐리', value=True)
    show_koo = st.checkbox('쿠우쿠우', value=True)
    st.markdown('---')
    st.markdown('**레이아웃** (지도 : 목록)')
    layout_opt = st.select_slider(
        '비율',
        options=['3:7', '4:6', '5:5', '6:4', '7:3'],
        value='6:4',
        label_visibility='collapsed'
    )
    if st.button('전국 보기 초기화', use_container_width=True):
        st.session_state.map_center = None
        st.session_state.map_zoom = 7
        st.session_state.selected_store = None
        st.rerun()

brands = tuple(b for b, on in [('샤브20', show_s20), ('애슐리', show_ash), ('쿠우쿠우', show_koo)] if on)
if not brands:
    st.warning('브랜드를 하나 이상 선택해주세요.')
    st.stop()

map_w, tbl_w = [int(x) for x in layout_opt.split(':')]

_, all_comps = load_data()
active_comps = all_comps[all_comps['브랜드'].isin(brands)]

result_df = compute_analysis(radius_km, brands)
sorted_df = result_df.sort_values('총계', ascending=False).reset_index(drop=True)
display_cols = ['매장명', '주소'] + list(brands) + ['총계']
display_df = sorted_df[display_cols].copy()

map_col, table_col = st.columns([map_w, tbl_w])

# ── Map column ────────────────────────────────────────────────────────────────
with map_col:
    center = st.session_state.map_center or [result_df['위도'].mean(), result_df['경도'].mean()]
    zoom   = st.session_state.map_zoom
    label  = f'지도  —  반경 {radius_km}km'
    if st.session_state.selected_store:
        label += f'  |  선택: {st.session_state.selected_store}'
    st.subheader(label)
    m = build_map(result_df, active_comps, radius_km, brands, center, zoom)
    st_folium(m, use_container_width=True, height=640, returned_objects=[])

# ── Table column ──────────────────────────────────────────────────────────────
with table_col:
    st.subheader('매장별 경쟁점 현황')
    st.caption(
        f'반경 {radius_km}km  ·  {len(sorted_df)}개 매장  ·  합계 많은 순  ·  '
        f'행 클릭 → 지도 이동'
    )

    gb = GridOptionsBuilder.from_dataframe(display_df)
    gb.configure_column('매장명', pinned='left', width=130, suppressMovable=True)
    gb.configure_column('주소', width=220)
    for brand in brands:
        gb.configure_column(brand, width=78, type=['numericColumn'])
    gb.configure_column('총계', width=72, type=['numericColumn'])
    gb.configure_selection('single', use_checkbox=False)
    gb.configure_grid_options(rowHeight=36, headerHeight=42, suppressRowClickSelection=False)
    grid_opts = gb.build()

    response = AgGrid(
        display_df,
        gridOptions=grid_opts,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        height=560,
        use_container_width=True,
        theme='streamlit',
    )

    # Row click → map zoom  (0.3.4 returns list of dicts)
    sel = response['selected_rows']
    if sel is not None:
        has_sel = len(sel) > 0
        sel_name = str(sel[0]['매장명']) if has_sel else None

        if has_sel and sel_name:
            match = result_df[result_df['매장명'] == sel_name]
            if not match.empty:
                new_center = [float(match.iloc[0]['위도']), float(match.iloc[0]['경도'])]
                if new_center != st.session_state.map_center:
                    st.session_state.map_center = new_center
                    st.session_state.map_zoom = 14
                    st.session_state.selected_store = sel_name
                    st.rerun()

    # Export
    buf = BytesIO()
    display_df.to_excel(buf, index=False)
    st.download_button(
        label='Excel로 내보내기',
        data=buf.getvalue(),
        file_name=f'샤브올데이_경쟁점분석_{radius_km}km.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        use_container_width=True,
    )
