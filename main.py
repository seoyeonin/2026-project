# -*- coding: utf-8 -*-
"""
서울시 권역별 실시간 대기환경정보 분석 대시보드
- 서울 열린데이터광장 OpenAPI(RealtimeCityAir) 사용
- 위치별 실시간 맞춤 행동 지침 & 카드뉴스 이미지 생성 지원
"""

import requests               # API 호출용
import pandas as pd           # 표/데이터 처리용
import numpy as np            # 숫자 계산용
import streamlit as st        # 웹 대시보드 UI
import plotly.express as px   # 지도 시각화용
import json                   # GeoJSON 읽기용
import os                     # 파일 경로 확인용
import io                     # 이미지 메모리 버퍼 처리용
from PIL import Image, ImageDraw, ImageFont # 카드뉴스 생성용
from datetime import datetime # 현재 시각 표시용
from zoneinfo import ZoneInfo # 한국 시간(Asia/Seoul) 계산용

# -------------------------------------------------------------------
# 0. 페이지 기본 설정
# -------------------------------------------------------------------
st.set_page_config(
    page_title="서울시 권역별 실시간 대기환경 대시보드",
    page_icon="🌫️",
    layout="wide",
)

# -------------------------------------------------------------------
# 1. 한국 시간(Asia/Seoul) 계산 및 상수 정의
# -------------------------------------------------------------------
KST = ZoneInfo("Asia/Seoul")
now_kst = datetime.now(KST)

SAREA_LIST = ["전체", "도심권", "동북권", "동남권", "서북권", "서남권"]

COLUMN_NAME_MAP = {
    "MSRMT_DT": "측정일시",
    "SAREA_NM": "권역명",
    "MSRSTN_NM": "측정소명",
    "PM": "미세먼지(㎍/㎥)",
    "FPM": "초미세먼지농도(㎍/㎥)",
    "OZON": "오존(ppm)",
    "NTDX": "이산화질소농도(ppm)",
    "CBMX": "일산화탄소농도(ppm)",
    "SPDX": "아황산가스농도(ppm)",
    "CAI_GRD": "통합대기환경등급",
    "CAI_IDX": "통합대기환경지수",
}

DISPLAY_COLUMNS_RAW = [
    "SAREA_NM", "PM", "FPM", "OZON", "NTDX", "CBMX", "SPDX", "CAI_GRD", "CAI_IDX"
]

NUMERIC_COLUMNS = ["PM", "FPM", "OZON", "NTDX", "CBMX", "SPDX", "CAI_IDX"]

SAREA_TO_GU = {
    "도심권": ["종로구", "중구", "용산구"],
    "동북권": ["노원구", "도봉구", "강북구", "성북구", "중랑구", "동대문구", "성동구", "광진구"],
    "동남권": ["서초구", "강남구", "송파구", "강동구"],
    "서북권": ["서대문구", "마포구", "은평구"],
    "서남권": ["강서구", "양천구", "영등포구", "동작구", "구로구", "금천구", "관악구"],
}

GU_TO_SAREA = {gu: sarea for sarea, gu_list in SAREA_TO_GU.items() for gu in gu_list}

GEOJSON_LOCAL_PATH = os.path.join(os.path.dirname(__file__), "data", "seoul_gu_boundaries.json")
GEOJSON_FALLBACK_URL = (
    "https://raw.githubusercontent.com/southkorea/seoul-maps/master/"
    "kostat/2013/json/seoul_municipalities_geo_simple.json"
)

# -------------------------------------------------------------------
# 2. 카드뉴스 이미지 생성 함수 (Pillow)
# -------------------------------------------------------------------
def generate_card_news(station_name, sarea_name, pm10, fpm, ozon, cai, cai_grd):
    width, height = 1080, 1080
    image = Image.new("RGB", (width, height), "#F8FAFC")
    draw = ImageDraw.Draw(image)

    font_paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
    ]
    
    selected_font_path = None
    for fp in font_paths:
        if os.path.exists(fp):
            selected_font_path = fp
            break

    def get_font(size):
        if selected_font_path:
            try:
                return ImageFont.truetype(selected_font_path, size)
            except:
                pass
        return ImageFont.load_default()

    font_title = get_font(42)
    font_subtitle = get_font(24)
    font_card_title = get_font(24)
    font_val = get_font(46)
    font_status = get_font(22)
    font_body = get_font(22)
    font_small = get_font(20)

    # 1) 헤더 배너
    draw.rounded_rectangle([40, 40, 1040, 180], radius=24, fill="#0F172A")
    draw.text((80, 65), "SEOUL AIR QUALITY DAILY REPORT", font=font_subtitle, fill="#38BDF8")
    draw.text((80, 105), "오늘의 서울시 대기환경 & 액션 플랜", font=font_title, fill="#FFFFFF")
    draw.text((750, 110), f"{station_name} ({sarea_name})", font=font_card_title, fill="#E2E8F0")

    # 2) 수치 카드 (2x2)
    pm10_val_str = f"{pm10:.0f} ug/m3" if pd.notnull(pm10) else "-"
    pm10_status = "나쁨" if pd.notnull(pm10) and pm10 > 80 else ("보통" if pd.notnull(pm10) and pm10 > 30 else "좋음")
    pm10_color = "#EF4444" if pd.notnull(pm10) and pm10 > 80 else ("#3B82F6" if pd.notnull(pm10) and pm10 > 30 else "#10B981")
    
    draw.rounded_rectangle([40, 210, 525, 380], radius=20, fill="#FFFFFF", outline="#E2E8F0", width=2)
    draw.text((70, 235), "미세먼지 (PM10)", font=font_card_title, fill="#64748B")
    draw.text((70, 280), pm10_val_str, font=font_val, fill="#0F172A")
    draw.rounded_rectangle([370, 235, 495, 275], radius=12, fill=pm10_color)
    draw.text((400, 243), pm10_status, font=font_status, fill="#FFFFFF")

    fpm_val_str = f"{fpm:.0f} ug/m3" if pd.notnull(fpm) else "-"
    fpm_status = "나쁨" if pd.notnull(fpm) and fpm > 35 else ("보통" if pd.notnull(fpm) and fpm > 15 else "좋음")
    fpm_color = "#EF4444" if pd.notnull(fpm) and fpm > 35 else ("#3B82F6" if pd.notnull(fpm) and fpm > 15 else "#10B981")

    draw.rounded_rectangle([555, 210, 1040, 380], radius=20, fill="#FFFFFF", outline="#E2E8F0", width=2)
    draw.text((585, 235), "초미세먼지 (PM2.5)", font=font_card_title, fill="#64748B")
    draw.text((585, 280), fpm_val_str, font=font_val, fill="#0F172A")
    draw.rounded_rectangle([885, 235, 1010, 275], radius=12, fill=fpm_color)
    draw.text((915, 243), fpm_status, font=font_status, fill="#FFFFFF")

    ozon_val_str = f"{ozon:.3f} ppm" if pd.notnull(ozon) else "-"
    ozon_status = "주의" if pd.notnull(ozon) and ozon >= 0.091 else "좋음"
    ozon_color = "#EF4444" if pd.notnull(ozon) and ozon >= 0.091 else "#10B981"

    draw.rounded_rectangle([40, 400, 525, 570], radius=20, fill="#FFFFFF", outline="#E2E8F0", width=2)
    draw.text((70, 425), "오존 (O3)", font=font_card_title, fill="#64748B")
    draw.text((70, 470), ozon_val_str, font=font_val, fill="#0F172A")
    draw.rounded_rectangle([370, 425, 495, 465], radius=12, fill=ozon_color)
    draw.text((400, 433), ozon_status, font=font_status, fill="#FFFFFF")

    cai_val_str = f"{cai:.0f} 점" if pd.notnull(cai) else "-"
    cai_color = "#EF4444" if pd.notnull(cai) and cai > 100 else ("#3B82F6" if pd.notnull(cai) and cai > 50 else "#10B981")

    draw.rounded_rectangle([555, 400, 1040, 570], radius=20, fill="#FFFFFF", outline="#E2E8F0", width=2)
    draw.text((585, 425), "통합대기환경지수 (CAI)", font=font_card_title, fill="#64748B")
    draw.text((585, 470), cai_val_str, font=font_val, fill="#0F172A")
    draw.rounded_rectangle([885, 425, 1010, 465], radius=12, fill=cai_color)
    draw.text((915, 433), str(cai_grd), font=font_status, fill="#FFFFFF")

    # 3) 행동 수칙
    draw.text((40, 605), "오늘의 추천 액션 플랜 (Action Plan)", font=font_card_title, fill="#0F172A")

    mask_txt = "외출 시 KF94/80 보건용 마스크를 착용하세요." if (pd.notnull(pm10) and pm10 > 80) or (pd.notnull(fpm) and fpm > 35) else "대기 상태 양호! 마스크 없이 일상 활동 가능합니다."
    draw.rounded_rectangle([40, 650, 1040, 735], radius=16, fill="#EFF6FF", outline="#BFDBFE", width=1)
    draw.text((65, 675), "[마스크 수칙]", font=font_card_title, fill="#1E40AF")
    draw.text((230, 677), mask_txt, font=font_body, fill="#1E293B")

    vent_txt = "창문을 열고 10분 이상 실내 환기를 시켜주세요." if pd.notnull(pm10) and pm10 <= 80 else "대기질이 나쁘므로 창문을 닫고 공기청정기를 가동하세요."
    draw.rounded_rectangle([40, 755, 1040, 840], radius=16, fill="#ECFDF5", outline="#A7F3D0", width=1)
    draw.text((65, 780), "[실내 환기]", font=font_card_title, fill="#065F46")
    draw.text((230, 782), vent_txt, font=font_body, fill="#1E293B")

    uv_txt = "야외 운동 추천! 외출 시 SPF30+ 선크림과 모자를 챙기세요." if pd.notnull(ozon) and ozon < 0.091 else "오존 농도가 높습니다. 한낮 야외활동을 자제하세요."
    draw.rounded_rectangle([40, 860, 1040, 945], radius=16, fill="#FFFBEB", outline="#FDE68A", width=1)
    draw.text((65, 885), "[야외/선크림]", font=font_card_title, fill="#92400E")
    draw.text((230, 887), uv_txt, font=font_body, fill="#1E293B")

    draw.text((40, 990), "데이터 출처: 서울 열린데이터광장 OpenAPI | 실시간 업데이트 (KST)", font=font_small, fill="#94A3B8")
    draw.text((780, 990), "2026 AIR DASHBOARD", font=font_small, fill="#64748B")

    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format="PNG")
    return img_byte_arr.getvalue()

# -------------------------------------------------------------------
# 3. GeoJSON 및 API 호출 함수
# -------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_seoul_geojson():
    if os.path.exists(GEOJSON_LOCAL_PATH):
        try:
            with open(GEOJSON_LOCAL_PATH, "r", encoding="utf-8") as f:
                return True, json.load(f), None
        except Exception as e:
            return False, None, f"지도 파일 읽기 실패: {e}"

    try:
        response = requests.get(GEOJSON_FALLBACK_URL, timeout=10)
        response.raise_for_status()
        return True, response.json(), None
    except Exception as e:
        return False, None, f"지도 내려받기 실패: {e}"

def build_gu_level_map_df(region_summary_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in region_summary_df.iterrows():
        sarea = row["SAREA_NM"]
        gu_list = SAREA_TO_GU.get(sarea, [])
        for gu in gu_list:
            new_row = row.to_dict()
            new_row["GU_NM"] = gu
            rows.append(new_row)
    return pd.DataFrame(rows)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_realtime_city_air(api_key: str, start_index: int, end_index: int, sarea_nm: str = None):
    base_url = f"http://openapi.seoul.go.kr:8088/{api_key}/json/RealtimeCityAir/{start_index}/{end_index}/"
    if sarea_nm and sarea_nm != "전체":
        base_url += f"{sarea_nm}/"

    try:
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return False, None, f"API 요청 중 오류가 발생했습니다: {e}"

    if "faultInfo" in data:
        return False, None, f"API 오류: {data['faultInfo'].get('message')}"
    if "RESULT" in data:
        return False, None, f"API 오류: {data['RESULT'].get('MESSAGE')}"

    service_data = data.get("RealtimeCityAir", {})
    row_list = service_data.get("row", [])
    if not row_list:
        return False, None, "조회 조건에 해당하는 데이터가 없습니다."

    return True, pd.DataFrame(row_list), None

def convert_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def build_region_summary(df: pd.DataFrame) -> pd.DataFrame:
    if "SAREA_NM" not in df.columns:
        return pd.DataFrame()
    numeric_cols_present = [c for c in NUMERIC_COLUMNS if c in df.columns and c != "CAI_IDX"] + (
        ["CAI_IDX"] if "CAI_IDX" in df.columns else []
    )
    summary = df.groupby("SAREA_NM")[numeric_cols_present].mean().reset_index()
    station_counts = df.groupby("SAREA_NM").size().reset_index(name="측정소 개수")
    return summary.merge(station_counts, on="SAREA_NM", how="left")

# -------------------------------------------------------------------
# 4. 사이드바 & 상단 헤더
# -------------------------------------------------------------------
st.sidebar.header("🔍 조회 조건")
api_key = st.secrets.get("SEOUL_KEY", None)
selected_sarea = st.sidebar.selectbox("권역 선택", SAREA_LIST, index=0)
start_index = st.sidebar.number_input("요청 시작 위치", min_value=1, value=1, step=1)
end_index = st.sidebar.number_input("요청 종료 위치", min_value=1, value=25, step=1)
refresh_clicked = st.sidebar.button("🔄 새로고침(다시 조회)", use_container_width=True)
st.sidebar.caption(f"현재 한국 시간(KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")

st.title("🌫️ 서울시 권역별 실시간 대기환경정보 대시보드")
st.caption(f"데이터 출처: 서울 열린데이터광장 OpenAPI · 기준 시각(KST): {now_kst.strftime('%Y년 %m월 %d일 %H시 %M분 %S초')}")

if not api_key:
    st.error("❌ 인증키를 찾을 수 없습니다. Streamlit Cloud의 Settings → Secrets 메뉴에서 SEOUL_KEY를 등록하세요.")
    st.stop()

if refresh_clicked:
    fetch_realtime_city_air.clear()

# -------------------------------------------------------------------
# 5. API 데이터 호출
# -------------------------------------------------------------------
with st.spinner("대기환경 데이터를 불러오는 중입니다..."):
    success, raw_df, error_message = fetch_realtime_city_air(
        api_key=api_key, start_index=int(start_index), end_index=int(end_index), sarea_nm=selected_sarea
    )

if not success:
    st.error(f"⚠️ 데이터를 불러오지 못했습니다.\n\n{error_message}")
    st.stop()

df = convert_numeric_columns(raw_df)

# -------------------------------------------------------------------
# 6. 탭 메인 UI 구현
# -------------------------------------------------------------------
tab1, tab2 = st.tabs(["📊 대시보드 & 지도", "🏃 위치별 맞춤 행동 지침 & 카드뉴스"])

# TAB 1: 종합 대시보드
with tab1:
    st.subheader("📊 요약 지표 (조회 결과 평균)")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("평균 미세먼지(㎍/㎥)", f"{df['PM'].mean():.1f}" if "PM" in df.columns else "-")
    col2.metric("평균 초미세먼지(㎍/㎥)", f"{df['FPM'].mean():.1f}" if "FPM" in df.columns else "-")
    col3.metric("평균 오존(ppm)", f"{df['OZON'].mean():.4f}" if "OZON" in df.columns else "-")
    col4.metric("평균 통합대기환경지수", f"{df['CAI_IDX'].mean():.1f}" if "CAI_IDX" in df.columns else "-")

    st.markdown("---")
    st.subheader("📋 요약표 (권역별 평균)")
    region_summary_df = build_region_summary(df)
    if not region_summary_df.empty:
        rs_display = region_summary_df.rename(columns=COLUMN_NAME_MAP)
        if "통합대기환경지수" in rs_display.columns:
            rs_display = rs_display.sort_values(by="통합대기환경지수", ascending=False, na_position="last")
        num_cols = [c for c in rs_display.columns if c not in ["권역명", "측정소 개수"]]
        rs_display[num_cols] = rs_display[num_cols].round(3)
        st.dataframe(rs_display, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📋 상세표 (측정소별)")
    dt_cols = [c for c in ["SAREA_NM", "MSRSTN_NM"] + [x for x in DISPLAY_COLUMNS_RAW if x != "SAREA_NM"] if c in df.columns]
    dt_table = df[dt_cols].copy().rename(columns=COLUMN_NAME_MAP)
    if "통합대기환경지수" in dt_table.columns:
        dt_table = dt_table.sort_values(by="통합대기환경지수", ascending=False, na_position="last")
    st.dataframe(dt_table, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("🗺️ 서울시 권역별 통합대기환경지수 지도")
    geo_success, geo_data, _ = load_seoul_geojson()
    if geo_success and not region_summary_df.empty and "CAI_IDX" in region_summary_df.columns:
        gu_map_df = build_gu_level_map_df(region_summary_df)
        if not gu_map_df.empty:
            common_kwargs = dict(
                data_frame=gu_map_df, geojson=geo_data, locations="GU_NM", featureidkey="properties.name",
                color="CAI_IDX", color_continuous_scale="YlOrRd", range_color=(0, max(100, gu_map_df["CAI_IDX"].max())),
                zoom=9.3, center={"lat": 37.5502, "lon": 126.982}, opacity=0.75, hover_name="GU_NM",
                hover_data={"SAREA_NM": True, "CAI_IDX": ":.1f", "GU_NM": False},
                labels={"CAI_IDX": "통합대기환경지수", "SAREA_NM": "권역명"},
            )
            try:
                fig = px.choropleth_map(map_style="carto-positron", **common_kwargs)
            except AttributeError:
                fig = px.choropleth_mapbox(mapbox_style="carto-positron", **common_kwargs)
            fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=520)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.subheader("📈 측정소별 통합대기환경지수")
        if "MSRSTN_NM" in df.columns and "CAI_IDX" in df.columns:
            st.bar_chart(df[["MSRSTN_NM", "CAI_IDX"]].dropna().sort_values(by="CAI_IDX", ascending=False).set_index("MSRSTN_NM"))

    with col_g2:
        st.subheader("📈 미세먼지 vs 초미세먼지")
        if "MSRSTN_NM" in df.columns and "PM" in df.columns and "FPM" in df.columns:
            st.bar_chart(df[["MSRSTN_NM", "PM", "FPM"]].dropna().set_index("MSRSTN_NM").rename(columns={"PM": "미세먼지", "FPM": "초미세먼지"}))

# TAB 2: 위치별 맞춤 행동 지침 & 카드뉴스
with tab2:
    st.subheader("📍 내 지역 실시간 대기지수 & 맞춤 행동 수칙")

    if "MSRSTN_NM" in df.columns and not df.empty:
        station_list = sorted(df["MSRSTN_NM"].unique().tolist())
        selected_station = st.selectbox("🎯 측정소(자치구)를 선택하세요:", station_list, index=0)

        target_data = df[df["MSRSTN_NM"] == selected_station].iloc[0]
        curr_sarea = target_data.get("SAREA_NM", "-")
        curr_pm = target_data.get("PM", np.nan)
        curr_fpm = target_data.get("FPM", np.nan)
        curr_ozon = target_data.get("OZON", np.nan)
        curr_cai = target_data.get("CAI_IDX", np.nan)
        curr_grd = target_data.get("CAI_GRD", "정보없음")

        st.markdown(f"### 🏢 [{selected_station}] ({curr_sarea}) 실시간 대기 상태")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("미세먼지(PM10)", f"{curr_pm} ㎍/㎥" if pd.notnull(curr_pm) else "-")
        c2.metric("초미세먼지(PM2.5)", f"{curr_fpm} ㎍/㎥" if pd.notnull(curr_fpm) else "-")
        c3.metric("오존(O₃)", f"{curr_ozon:.3f} ppm" if pd.notnull(curr_ozon) else "-")
        c4.metric("통합대기지수", f"{curr_cai:.0f}" if pd.notnull(curr_cai) else "-", delta=curr_grd)

        st.markdown("---")
        st.subheader("📋 실시간 추천 액션 플랜 (Action Plan)")

        # 수칙 1: 마스크
        st.markdown("#### 😷 1. 마스크 착용 수칙")
        if (pd.notnull(curr_pm) and curr_pm > 80) or (pd.notnull(curr_fpm) and curr_fpm > 35):
            st.error("🚨 **[경고] 미세먼지 '나쁨' 이상!** 외출 시 **KF94/80 마스크**를 반드시 착용하세요.")
        else:
            st.success("🟢 **[쾌적] 공기 상태 양호!** 마스크 없이 자유롭게 야외활동을 하셔도 좋습니다.")

        # 수칙 2: 환기
        st.markdown("#### 🪟 2. 실내 환기 수칙")
        if pd.notnull(curr_pm) and curr_pm > 80:
            st.warning("⚠️ **[환기 자제]** 대기 오염이 심하므로 창문을 닫고 공기청정기를 가동하세요.")
        else:
            st.success("✨ **[환기 추천]** 맞바람이 통하도록 10분 이상 실내 환기를 실시하세요.")

        # 수칙 3: 오존/선크림
        st.markdown("#### ☀️ 3. 오존 및 선크림 수칙")
        if pd.notnull(curr_ozon) and curr_ozon >= 0.091:
            st.error("🔴 **[오존 주의]** 오후 2시~5시 사이 야외활동을 자제하고 외출 시 **선크림**을 바르세요.")
        else:
            st.info("🧴 **[선크림 권장]** 야외 활동 시 **자외선 차단제(선크림)**를 발라 피부를 보호하세요.")

        # ---------------------------------------------------------------
        # SNS 카드뉴스 생성 & 다운로드 버튼
        # ---------------------------------------------------------------
        st.markdown("---")
        st.subheader("📸 SNS 공유용 카드뉴스 생성")
        st.write("오늘의 대기 수치와 추천 수칙을 1080x1080 이미지로 생성하여 공유할 수 있습니다.")

        if st.button("✨ 실시간 카드뉴스 만들기", use_container_width=True):
            with st.spinner("카드뉴스 이미지를 그리는 중입니다..."):
                card_img_bytes = generate_card_news(
                    station_name=selected_station,
                    sarea_name=curr_sarea,
                    pm10=curr_pm,
                    fpm=curr_fpm,
                    ozon=curr_ozon,
                    cai=curr_cai,
                    cai_grd=curr_grd
                )
                
                st.image(card_img_bytes, caption=f"[{selected_station}] 실시간 대기 상태 카드뉴스", use_container_width=True)
                
                st.download_button(
                    label="💾 카카오톡 / 인스타그램 공유용 이미지 다운로드",
                    data=card_img_bytes,
                    file_name=f"서울시_대기환경_카드뉴스_{selected_station}.png",
                    mime="image/png",
                    use_container_width=True
                )
    else:
        st.info("측정소 데이터를 불러올 수 없습니다.")

st.caption("본 데이터는 참고용이며, 상세 대기 환경 정보는 환경부 및 서울시 공식 발표를 확인하세요.")
