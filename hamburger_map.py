import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from io import BytesIO
from collections import defaultdict
st.set_page_config(
    page_title='햄버거 경쟁점 분석',
    page_icon='🍔',
    layout='wide',
    initial_sidebar_state='collapsed',
)

for key, default in [('map_center', None), ('map_zoom', 7), ('selected_id', None), ('mode', 'single')]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Brand config ───────────────────────────────────────────────────────────────

ALL_BRANDS = ['프랭크버거', '버거킹', '맥도날드', '롯데리아', '맘스터치', 'KFC', '노브랜드버거']

BRAND_CFG = {
    '프랭크버거':   {'hex': '#2E7D32', 'folium': 'green',   'folium_sel': 'darkgreen'},
    '버거킹':       {'hex': '#E65100', 'folium': 'orange',  'folium_sel': 'darkred'},
    '맥도날드':     {'hex': '#F9A825', 'folium': 'beige',   'folium_sel': 'orange'},
    '롯데리아':     {'hex': '#1565C0', 'folium': 'blue',    'folium_sel': 'darkblue'},
    '맘스터치':     {'hex': '#AD1457', 'folium': 'pink',    'folium_sel': 'red'},
    'KFC':          {'hex': '#4E342E', 'folium': 'darkred', 'folium_sel': 'darkred'},
    '노브랜드버거': {'hex': '#546E7A', 'folium': 'gray',    'folium_sel': 'black'},
}

# ── Utilities ──────────────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2_arr, lon2_arr):
    R = 6371.0
    rlat1, rlon1 = np.radians(lat1), np.radians(lon1)
    rlat2 = np.radians(np.asarray(lat2_arr, dtype=float))
    rlon2 = np.radians(np.asarray(lon2_arr, dtype=float))
    a = np.sin((rlat2 - rlat1) / 2)**2 + np.cos(rlat1) * np.cos(rlat2) * np.sin((rlon2 - rlon1) / 2)**2
    return 2 * R * np.arcsin(np.sqrt(a))

@st.cache_data
def load_data():
    BASE = 'Hamburger Competitors'
    dfs = {}

    df = pd.read_excel(f'{BASE}/Frank_Korea_All_Stores_26-04-28_정리.xlsx')
    dfs['프랭크버거'] = df.dropna(subset=['위도', '경도'])[['매장명', '주소', '위도', '경도']].reset_index(drop=True)

    df = pd.read_excel(f'{BASE}/BurgerKing_Korea_All_Stores_26-04-28.xlsx')
    df = df.rename(columns={'매장명 Store Name': '매장명', '주소 Address': '주소'})
    dfs['버거킹'] = df.dropna(subset=['위도', '경도'])[['매장명', '주소', '위도', '경도']].reset_index(drop=True)

    df = pd.read_excel(f'{BASE}/McDonalds_Korea_All_Stores_26-04-28.xlsx')
    df = df.rename(columns={'매장명 (Korean)': '매장명', '주소 Address (Korean)': '주소', 'Latitude': '위도', 'Longitude': '경도'})
    dfs['맥도날드'] = df.dropna(subset=['위도', '경도'])[['매장명', '주소', '위도', '경도']].reset_index(drop=True)

    df = pd.read_csv(f'{BASE}/Lotteria_Korea_All_Stores_1250.csv')
    df = df.rename(columns={'Latitude': '위도', 'Longitude': '경도'})
    dfs['롯데리아'] = df.dropna(subset=['위도', '경도'])[['매장명', '주소', '위도', '경도']].reset_index(drop=True)

    df = pd.read_excel(f'{BASE}/MomsTouch_Korea_All_Stores_26-04-28.xlsx')
    if '위도' not in df.columns:
        df['위도'] = None
        df['경도'] = None
    dfs['맘스터치'] = df.dropna(subset=['위도', '경도'])[['매장명', '주소', '위도', '경도']].reset_index(drop=True)

    df = pd.read_excel(f'{BASE}/KFC_Korea_All_Stores_26-04-28.xlsx')
    df = df.rename(columns={'도로명주소': '주소'})
    if '위도' not in df.columns:
        df['위도'] = None
        df['경도'] = None
    dfs['KFC'] = df.dropna(subset=['위도', '경도'])[['매장명', '주소', '위도', '경도']].reset_index(drop=True)

    df = pd.read_excel(f'{BASE}/NoBrandBurger_Korea_All_Stores_26-04-28.xlsx')
    if '위도' not in df.columns:
        df['위도'] = None
        df['경도'] = None
    dfs['노브랜드버거'] = df.dropna(subset=['위도', '경도'])[['매장명', '주소', '위도', '경도']].reset_index(drop=True)

    return dfs

# ── Analysis: single mode ─────────────────────────────────────────────────────

@st.cache_data
def compute_single(subject: str, radius_km: float):
    dfs = load_data()
    subject_df = dfs[subject]
    others = [b for b in ALL_BRANDS if b != subject]

    rows = []
    for _, store in subject_df.iterrows():
        row = {'매장명': store['매장명'], '주소': store['주소'],
               '위도': store['위도'], '경도': store['경도']}
        nearby_by_brand = {}
        total = 0
        for brand in others:
            comp = dfs[brand]
            if len(comp) == 0:
                nearby_by_brand[brand] = []
                row[brand] = 0
                continue
            dists = haversine(store['위도'], store['경도'], comp['위도'].values, comp['경도'].values)
            mask = dists <= radius_km
            nb = comp[mask].copy()
            nb['거리_km'] = dists[mask]
            nb = nb.sort_values('거리_km')
            nearby_by_brand[brand] = list(zip(nb['매장명'], nb['거리_km']))
            cnt = len(nearby_by_brand[brand])
            row[brand] = cnt
            total += cnt
        row['총계'] = total
        row['_nearby'] = nearby_by_brand
        rows.append(row)

    return pd.DataFrame(rows)

# ── Analysis: district mode ───────────────────────────────────────────────────

@st.cache_data
def compute_districts(include_brands: tuple, exclude_brands: tuple, radius_km: float):
    if len(include_brands) < 2:
        return []

    dfs = load_data()
    inc = list(include_brands)
    exc = list(exclude_brands)

    nodes = []
    for brand in inc:
        for _, row in dfs[brand].iterrows():
            nodes.append((brand, float(row['위도']), float(row['경도']),
                          row['매장명'], row['주소']))

    n = len(nodes)
    if n == 0:
        return []

    lats = np.array([nd[1] for nd in nodes])
    lons = np.array([nd[2] for nd in nodes])

    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        dists = haversine(lats[i], lons[i], lats[i+1:], lons[i+1:])
        for offset in np.where(dists <= radius_km)[0]:
            union(i, i + 1 + int(offset))

    comps = defaultdict(list)
    for i in range(n):
        comps[find(i)].append(i)

    districts = []
    for members in comps.values():
        brands_in = {nodes[i][0] for i in members}
        if not all(b in brands_in for b in inc):
            continue

        m_lats = lats[members]
        m_lons = lons[members]
        excluded = False
        for exc_brand in exc:
            exc_df = dfs.get(exc_brand, pd.DataFrame())
            if len(exc_df) == 0:
                continue
            for lat, lon in zip(m_lats, m_lons):
                if np.any(haversine(lat, lon, exc_df['위도'].values, exc_df['경도'].values) <= radius_km):
                    excluded = True
                    break
            if excluded:
                break
        if excluded:
            continue

        stores_by_brand = {b: [] for b in inc}
        for i in members:
            brand, lat, lon, name, addr = nodes[i]
            stores_by_brand[brand].append({'name': name, 'lat': lat, 'lon': lon, 'addr': addr})

        districts.append({
            'centroid': (float(np.mean(m_lats)), float(np.mean(m_lons))),
            'stores': stores_by_brand,
            'counts': {b: len(stores_by_brand[b]) for b in inc},
            'total': len(members),
        })

    districts.sort(key=lambda d: d['total'], reverse=True)
    for i, d in enumerate(districts):
        d['id'] = i + 1

    return districts

# ── Map builders ───────────────────────────────────────────────────────────────

def _legend(brands, radius_km, subject_label):
    items = [f'<span style="color:{BRAND_CFG[subject_label]["hex"]}">★</span> {subject_label}'] + [
        f'<span style="color:{BRAND_CFG[b]["hex"]}">●</span> {b}' for b in brands
    ] + [f'<span style="color:{BRAND_CFG[subject_label]["hex"]}">○</span> 반경 {radius_km}km']
    return (
        '<div style="position:fixed;bottom:30px;right:10px;z-index:1000;background:white;'
        'padding:10px 16px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);'
        'font-size:13px;line-height:1.9">'
        '<b>범례</b><br>' + '<br>'.join(items) + '</div>'
    )

def build_single_map(subject: str, radius_km: float):
    dfs = load_data()
    result_df = compute_single(subject, radius_km)
    others = [b for b in ALL_BRANDS if b != subject]

    m = folium.Map(location=[36.5, 127.8], zoom_start=7, tiles='cartodbpositron')

    # Competitor dots — clustered per brand
    for brand in others:
        hex_c = BRAND_CFG[brand]['hex']
        cluster = MarkerCluster(
            name=brand,
            options={'maxClusterRadius': 30, 'disableClusteringAtZoom': 13}
        ).add_to(m)
        for _, row in dfs[brand].iterrows():
            folium.CircleMarker(
                location=[row['위도'], row['경도']],
                radius=5, color=hex_c, fill_color=hex_c,
                fill=True, fill_opacity=0.75, weight=1,
                popup=folium.Popup(
                    f"<b>[{brand}]</b> {row['매장명']}<br><small>{row['주소']}</small>",
                    max_width=220),
                tooltip=f"[{brand}] {row['매장명']}"
            ).add_to(cluster)

    subj_hex = BRAND_CFG[subject]['hex']
    subj_col = BRAND_CFG[subject]['folium']

    for _, store in result_df.iterrows():
        nearby_html = ''
        for brand in others:
            nb = store['_nearby'].get(brand, [])
            if nb:
                items = ''.join(f'<li>{nm} <span style="color:#888">({d:.1f}km)</span></li>' for nm, d in nb)
                nearby_html += (
                    f'<div style="margin:3px 0"><span style="color:{BRAND_CFG[brand]["hex"]};font-weight:bold">'
                    f'{brand} ({len(nb)})</span>'
                    f'<ul style="margin:2px 0;padding-left:14px;line-height:1.5">{items}</ul></div>'
                )

        popup_html = (
            f'<div style="font-family:sans-serif;font-size:13px;width:280px;max-height:380px;overflow-y:auto">'
            f'<b style="font-size:14px;color:{subj_hex}">{store["매장명"]}</b><br>'
            f'<small style="color:#666">{store["주소"]}</small>'
            f'<hr style="margin:5px 0"><b>반경 {radius_km}km 이내</b>'
            f'{nearby_html or "<p style=color:#999>없음</p>"}'
            f'</div>'
        )
        folium.Marker(
            [store['위도'], store['경도']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"[{subject}] {store['매장명']}  (경쟁점 {store['총계']}개)",
            icon=folium.Icon(color=subj_col, icon='star', prefix='glyphicon')
        ).add_to(m)
        folium.Circle(
            [store['위도'], store['경도']], radius=radius_km * 1000,
            color=subj_hex, fill=True, fill_opacity=0.05, weight=1.5
        ).add_to(m)

    m.get_root().html.add_child(folium.Element(_legend(others, radius_km, subject)))
    return m

def build_district_map(include_brands: tuple, exclude_brands: tuple, radius_km: float):
    districts = compute_districts(include_brands, exclude_brands, radius_km)
    dfs = load_data()
    m = folium.Map(location=[36.5, 127.8], zoom_start=7, tiles='cartodbpositron')

    # Track which selected-brand stores are in districts (so we don't draw them
    # twice — once as background and once as halo).
    district_keys = set()
    for d in districts:
        for b in include_brands:
            for s in d['stores'][b]:
                district_keys.add((b, round(s['lat'], 6), round(s['lon'], 6)))

    # Background layer 1: unselected brands (small, faded)
    for brand in ALL_BRANDS:
        if brand in include_brands:
            continue
        hex_c = BRAND_CFG[brand]['hex']
        cluster = MarkerCluster(
            name=brand,
            options={'maxClusterRadius': 30, 'disableClusteringAtZoom': 13}
        ).add_to(m)
        for _, row in dfs[brand].iterrows():
            folium.CircleMarker(
                location=[row['위도'], row['경도']],
                radius=4, color=hex_c, fill_color=hex_c,
                fill=True, fill_opacity=0.35, weight=1,
                popup=folium.Popup(
                    f"<b>[{brand}]</b> {row['매장명']}<br><small>{row['주소']}</small>",
                    max_width=220),
                tooltip=f"[{brand}] {row['매장명']}"
            ).add_to(cluster)

    # Background layer 2: selected-brand stores NOT in any district (faded)
    for brand in include_brands:
        hex_c = BRAND_CFG[brand]['hex']
        cluster = MarkerCluster(
            name=brand,
            options={'maxClusterRadius': 30, 'disableClusteringAtZoom': 13}
        ).add_to(m)
        for _, row in dfs[brand].iterrows():
            key = (brand, round(float(row['위도']), 6), round(float(row['경도']), 6))
            if key in district_keys:
                continue
            folium.CircleMarker(
                location=[row['위도'], row['경도']],
                radius=4, color=hex_c, fill_color=hex_c,
                fill=True, fill_opacity=0.4, weight=1,
                popup=folium.Popup(
                    f"<b>[{brand}]</b> {row['매장명']}<br><small>{row['주소']}</small>",
                    max_width=220),
                tooltip=f"[{brand}] {row['매장명']}"
            ).add_to(cluster)

    # Foreground: districts (purple circles + labels) and the highlighted member
    # stores (white halo + brand fill — visually pops above the background dots)
    for d in districts:
        clat, clon = d['centroid']

        count_html = ''.join(
            f'<tr><td style="color:{BRAND_CFG[b]["hex"]};padding:2px 6px">{b}</td>'
            f'<td align="right" style="padding:2px 6px"><b>{d["counts"][b]}</b>개</td></tr>'
            for b in include_brands
        )
        store_html = ''.join(
            f'<li><span style="color:{BRAND_CFG[b]["hex"]}">[{b}]</span> {s["name"]}</li>'
            for b in include_brands for s in d['stores'][b]
        )
        popup_html = (
            f'<div style="font-family:sans-serif;font-size:13px;width:250px;max-height:350px;overflow-y:auto">'
            f'<b>District #{d["id"]}</b> — 총 {d["total"]}개 매장'
            f'<table style="width:100%;margin:4px 0">{count_html}</table>'
            f'<hr style="margin:4px 0"><b>매장 목록</b>'
            f'<ul style="margin:4px 0;padding-left:14px;line-height:1.6">{store_html}</ul>'
            f'</div>'
        )

        folium.Circle(
            [clat, clon], radius=radius_km * 1000,
            color='#7B1FA2', weight=1.5,
            fill=True, fill_opacity=0.07,
            popup=folium.Popup(popup_html, max_width=270),
            tooltip=f"District #{d['id']}  ({d['total']}개)"
        ).add_to(m)
        folium.Marker(
            [clat, clon],
            tooltip=f"District #{d['id']}  ({d['total']}개)",
            icon=folium.DivIcon(
                html=f'<div style="font-size:11px;font-weight:bold;color:#7B1FA2;'
                     f'background:white;border:1.5px solid #7B1FA2;border-radius:10px;'
                     f'padding:1px 5px;white-space:nowrap">D{d["id"]}</div>',
                icon_size=(30, 18), icon_anchor=(15, 9)
            )
        ).add_to(m)

        for b in include_brands:
            hex_c = BRAND_CFG[b]['hex']
            for s in d['stores'][b]:
                folium.CircleMarker(
                    location=[s['lat'], s['lon']],
                    radius=7, color='white', fill_color=hex_c,
                    fill=True, fill_opacity=0.95, weight=2.5,
                    popup=folium.Popup(
                        f"<b>[{b}]</b> {s['name']}<br><small>{s['addr']}</small>",
                        max_width=220),
                    tooltip=f"[{b}] {s['name']}"
                ).add_to(m)

    legend_items = (
        ['<span style="color:#7B1FA2">○</span> District (반경 ' + str(radius_km) + 'km)']
        + [f'<span style="color:{BRAND_CFG[b]["hex"]}">◉</span> {b} (✓ 포함)' for b in include_brands]
        + [f'<span style="color:{BRAND_CFG[b]["hex"]}">·</span> {b}' for b in ALL_BRANDS if b not in include_brands]
    )
    legend_html = (
        '<div style="position:fixed;bottom:30px;right:10px;z-index:1000;background:white;'
        'padding:10px 16px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);'
        'font-size:13px;line-height:1.9">'
        '<b>범례</b><br>' + '<br>'.join(legend_items) + '</div>'
    )
    m.get_root().html.add_child(folium.Element(legend_html))
    return m

# ── UI ─────────────────────────────────────────────────────────────────────────

st.title('🍔 햄버거 경쟁점 분석')

# ── Franchise selector row ────────────────────────────────────────────────────

st.markdown(
    '**브랜드 선택**  \n'
    '· **✓ 1개** → 해당 브랜드의 매장별 경쟁점 현황 분석  \n'
    '· **✓ 2개 이상** → ✓ 브랜드가 모두 반경 내에 공존하는 구역(**District**) 탐색  \n'
    '· **✗** 표시한 브랜드가 District 인근에 있으면 그 구역은 제외 (✗는 ✓가 2개 이상일 때만 적용)'
)
brand_cols = st.columns(len(ALL_BRANDS))
include_brands = []
exclude_brands_list = []

for i, brand in enumerate(ALL_BRANDS):
    with brand_cols[i]:
        st.markdown(
            f'<div style="text-align:center;font-weight:bold;font-size:12px;'
            f'color:{BRAND_CFG[brand]["hex"]};padding:2px 0;line-height:1.2">{brand}</div>',
            unsafe_allow_html=True
        )
        inc = st.checkbox('✓ 포함', key=f'inc_{brand}', value=(brand == '프랭크버거'))
        exc = st.checkbox('✗ 제외', key=f'exc_{brand}', value=False)
        if inc and exc:
            st.caption(':red[충돌] ✗ 무시됨')
            exc = False
        if inc:
            include_brands.append(brand)
        elif exc:
            exclude_brands_list.append(brand)

if not include_brands:
    st.warning('브랜드를 하나 이상 ✓ 선택해주세요.')
    st.stop()


st.markdown('---')

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header('분석 설정')
    radius_km = st.slider('반경 (km)', min_value=0.5, max_value=10.0, value=0.5, step=0.5)
    st.markdown('---')
    st.markdown('**레이아웃** (지도 : 목록)')
    layout_opt = st.select_slider(
        '비율',
        options=['3:7', '4:6', '5:5', '6:4', '7:3'],
        value='6:4',
        label_visibility='collapsed'
    )
    if st.button('전국 보기 초기화', use_container_width=True):
        st.session_state.map_center  = None
        st.session_state.map_zoom    = 7
        st.session_state.selected_id = None
        st.rerun()

map_w, tbl_w = [int(x) for x in layout_opt.split(':')]

# ── Determine mode ────────────────────────────────────────────────────────────

single_mode = (len(include_brands) == 1)
# ✗ exclude only applies in district mode (when ≥2 ✓ brands are selected)
exclude_brands = exclude_brands_list if not single_mode else []
subject = include_brands[0] if single_mode else None
inc_tuple = tuple(include_brands)
exc_tuple = tuple(exclude_brands)

# ── Compute ───────────────────────────────────────────────────────────────────

if single_mode:
    result_df = compute_single(subject, radius_km)
    all_lats = result_df['위도']
    all_lons = result_df['경도']
else:
    districts = compute_districts(inc_tuple, exc_tuple, radius_km)
    dfs_loaded = load_data()
    all_lats = pd.concat([dfs_loaded[b]['위도'] for b in include_brands])
    all_lons = pd.concat([dfs_loaded[b]['경도'] for b in include_brands])
    result_df = None

if not single_mode:
    brands_str = ' + '.join(include_brands)
    st.info(
        f'**District 모드** — ✓ 선택한 브랜드({brands_str})가 모두 반경 **{radius_km}km** 이내에 '
        f'공존하는 구역을 표시합니다. 선택하지 않은 브랜드가 인근에 있는 구역은 자동으로 제외됩니다.  \n'
        f'현재 조건 충족 구역: **{len(districts)}개**'
    )

map_col, table_col = st.columns([map_w, tbl_w])

# ── Map column ────────────────────────────────────────────────────────────────

with map_col:
    center = st.session_state.map_center or [float(all_lats.mean()), float(all_lons.mean())]
    zoom   = st.session_state.map_zoom
    if single_mode:
        label = f'지도  —  반경 {radius_km}km'
        if st.session_state.selected_id:
            label += f'  |  선택: {st.session_state.selected_id}'
    else:
        label = f'지도  —  반경 {radius_km}km  |  District {len(districts)}개'
    st.subheader(label)

    if single_mode:
        m = build_single_map(subject, radius_km)
        map_key = f'map_s_{subject}_{radius_km}'
    else:
        m = build_district_map(inc_tuple, exc_tuple, radius_km)
        map_key = f'map_d_{"_".join(inc_tuple)}_{radius_km}'

    st_folium(m, center=center, zoom=zoom,
              use_container_width=True, height=640, returned_objects=[],
              key=map_key)

# ── Table column ──────────────────────────────────────────────────────────────

with table_col:
    if single_mode:
        # ── Single mode table ─────────────────────────────────────────────────
        others = [b for b in ALL_BRANDS if b != subject]
        sorted_df = result_df.sort_values('총계', ascending=False).reset_index(drop=True)
        display_cols = ['매장명', '주소'] + others + ['총계']
        display_df = sorted_df[display_cols].copy()

        st.subheader(f'{subject}  매장별 경쟁점 현황')
        st.caption(f'반경 {radius_km}km  ·  {len(sorted_df)}개 매장  ·  합계 많은 순  ·  행 클릭 → 지도 이동')

        gb = GridOptionsBuilder.from_dataframe(display_df)
        gb.configure_column('매장명', pinned='left', width=130, suppressMovable=True)
        gb.configure_column('주소', width=200)
        for brand in others:
            gb.configure_column(brand, width=80, type=['numericColumn'])
        gb.configure_column('총계', width=72, type=['numericColumn'])
        gb.configure_selection('single', use_checkbox=False)
        gb.configure_grid_options(rowHeight=36, headerHeight=42, suppressRowClickSelection=False)

        response = AgGrid(
            display_df,
            gridOptions=gb.build(),
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            height=480,
            use_container_width=True,
            theme='streamlit',
        )

        sel = response['selected_rows']
        if sel is not None and len(sel) > 0:
            sel_name = str(sel[0]['매장명'])
            match = result_df[result_df['매장명'] == sel_name]
            if not match.empty:
                new_center = [float(match.iloc[0]['위도']), float(match.iloc[0]['경도'])]
                if new_center != st.session_state.map_center or sel_name != st.session_state.selected_id:
                    st.session_state.map_center  = new_center
                    st.session_state.map_zoom    = 14
                    st.session_state.selected_id = sel_name
                    st.rerun()

            # Detail panel: nearby store names
            nearby = match.iloc[0]['_nearby']
            with st.expander(f'📍 {sel_name} — 반경 {radius_km}km 경쟁점 상세', expanded=True):
                has_any = False
                for brand in others:
                    nb = nearby.get(brand, [])
                    if nb:
                        has_any = True
                        hex_c = BRAND_CFG[brand]['hex']
                        st.markdown(
                            f'<span style="color:{hex_c};font-weight:bold">{brand}</span> ({len(nb)}개)',
                            unsafe_allow_html=True
                        )
                        for nm, dist in nb:
                            st.markdown(f'&nbsp;&nbsp;&nbsp;• {nm} `{dist:.2f}km`', unsafe_allow_html=True)
                if not has_any:
                    st.caption('반경 내 경쟁점 없음')

        # Export — counts AND nearby store names per brand (with distances)
        export_rows = []
        for _, r in sorted_df.iterrows():
            out = {'매장명': r['매장명'], '주소': r['주소']}
            for brand in others:
                out[brand] = r[brand]
                nb = r['_nearby'].get(brand, [])
                out[f'{brand} 매장'] = ', '.join(f'{nm} ({d:.2f}km)' for nm, d in nb)
            out['총계'] = r['총계']
            export_rows.append(out)
        export_df = pd.DataFrame(export_rows)
        buf = BytesIO()
        export_df.to_excel(buf, index=False)
        st.download_button(
            label='Excel로 내보내기',
            data=buf.getvalue(),
            file_name=f'{subject}_경쟁점분석_{radius_km}km.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            use_container_width=True,
        )

    else:
        # ── District mode table ───────────────────────────────────────────────
        st.subheader('District 분석')
        exc_label = f'  ·  제외: {", ".join(exclude_brands)}' if exclude_brands else ''
        st.caption(
            f'반경 {radius_km}km  ·  포함: {", ".join(include_brands)}{exc_label}  ·  '
            f'{len(districts)}개 구역 발견  ·  행 클릭 → 지도 이동'
        )

        if not districts:
            st.info('조건에 맞는 District가 없습니다. 반경을 늘리거나 브랜드 조합을 변경해보세요.')
        else:
            dist_rows = []
            for d in districts:
                row = {'District': f'D{d["id"]}', '위도': d['centroid'][0], '경도': d['centroid'][1]}
                for b in include_brands:
                    row[b] = d['counts'][b]
                row['총계'] = d['total']
                dist_rows.append(row)
            dist_df = pd.DataFrame(dist_rows)

            gb = GridOptionsBuilder.from_dataframe(dist_df)
            gb.configure_column('District', pinned='left', width=80, suppressMovable=True)
            gb.configure_column('위도', hide=True)
            gb.configure_column('경도', hide=True)
            for b in include_brands:
                gb.configure_column(b, width=80, type=['numericColumn'])
            gb.configure_column('총계', width=72, type=['numericColumn'])
            gb.configure_selection('single', use_checkbox=False)
            gb.configure_grid_options(rowHeight=36, headerHeight=42, suppressRowClickSelection=False)

            response = AgGrid(
                dist_df,
                gridOptions=gb.build(),
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                height=480,
                use_container_width=True,
                theme='streamlit',
            )

            sel = response['selected_rows']
            if sel is not None and len(sel) > 0:
                sel_did_str = str(sel[0]['District'])
                sel_did = int(sel_did_str[1:])
                new_center = [float(sel[0]['위도']), float(sel[0]['경도'])]
                if new_center != st.session_state.map_center or sel_did != st.session_state.selected_id:
                    st.session_state.map_center  = new_center
                    st.session_state.map_zoom    = 14
                    st.session_state.selected_id = sel_did
                    st.rerun()

                d_match = next((d for d in districts if d['id'] == sel_did), None)
                if d_match:
                    with st.expander(f'📍 {sel_did_str} 매장 목록', expanded=True):
                        for b in include_brands:
                            stores = d_match['stores'][b]
                            if stores:
                                hex_c = BRAND_CFG[b]['hex']
                                st.markdown(
                                    f'<span style="color:{hex_c};font-weight:bold">{b}</span> ({len(stores)}개)',
                                    unsafe_allow_html=True
                                )
                                for s in stores:
                                    st.markdown(f'&nbsp;&nbsp;&nbsp;• {s["name"]}', unsafe_allow_html=True)

            # Export — counts AND store names per brand for each district
            export_rows = []
            for d in districts:
                out = {'District': f'D{d["id"]}'}
                for b in include_brands:
                    out[b] = d['counts'][b]
                    out[f'{b} 매장'] = ', '.join(s['name'] for s in d['stores'][b])
                out['총계'] = d['total']
                export_rows.append(out)
            export_df = pd.DataFrame(export_rows)
            buf = BytesIO()
            export_df.to_excel(buf, index=False)
            st.download_button(
                label='Excel로 내보내기',
                data=buf.getvalue(),
                file_name=f'District분석_{"_".join(include_brands)}_{radius_km}km.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True,
            )
