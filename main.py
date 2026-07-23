# -*- coding: utf-8 -*-
"""
서울시 권역별 실시간 대기환경정보 분석 대시보드 (맞춤 행동지침 탭 포함)
- 서울 열린데이터광장 OpenAPI(RealtimeCityAir) 사용
- Streamlit Cloud 배포 전제로 작성
"""

import requests               # API 호출용 라이브러리
import pandas as pd           # 표/데이터 처리용 라이브러리
import numpy as np            # 숫자 계산용 라이브러리
import streamlit as st        # 웹 대시보드 UI 라이브러리
import plotly.express as px   # 지도(코로플레스) 시각화용 라이브러리
import json                   # GeoJSON 파일을 읽기 위한 라이브러리
import os                     # 파일 경로 확인용 라이브러리
from datetime import datetime # 현재 시각 표시용
from zoneinfo import ZoneInfo # 한국 시간(Asia/Seoul) 계산용 (표준 라이브러리)

# -------------------------------------------------------------------
# 0. 페이지 기본 설정
# -------------------------------------------------------------------
st.set_page_config(
    page_title="서울시 권역별 실시간 대기환경 대시보드",
    page_icon="🌫️",
    layout="wide",
)

# -------------------------------------------------------------------
# 1. 한국 시간(Asia/Seoul) 계산
# -------------------------------------------------------------------
KST = ZoneInfo("Asia/Seoul")
now_kst = datetime.now(KST)

# -------------------------------------------------------------------
# 2. 화면에 쓰일 상수값 정의
# -------------------------------------------------------------------
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

# -------------------------------------------------------------------
# 2-1. 서울시 5개 권역 ↔ 25개 자치구 매핑
# -------------------------------------------------------------------
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


@st.cache_data(show_spinner=False)
def load_seoul_geojson():
    if os.path.exists(GEOJSON_LOCAL_PATH):
        try:
            with open(GEOJSON_LOCAL_PATH, "r", encoding="utf-8") as f:
                return True, json.load(f), None
        except Exception as e:
            return False, None, f"지도 경계 파일을 읽는 데 실패했습니다. (오류 내용: {e})"

    try:
        response = requests.get(GEOJSON_FALLBACK_URL, timeout=10)
        response.raise_for_status()
        return True, response.json(), None
    except Exception as e:
        return False, None, f"지도 경계 데이터를 내려받지 못했습니다. (오류 내용: {e})"


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


# -------------------------------------------------------------------
# 3. API 호출 함수
# -------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_realtime_city_air(api_key: str, start_index: int, end_index: int, sarea_nm: str = None):
    base_url = (
        f"http://openapi.seoul.go.kr:8088/{api_key}/json/"
        f"RealtimeCityAir/{start_index}/{end_index}/"
    )

    if sarea_nm and sarea_nm != "전체":
        base_url += f"{sarea_nm}/"

    try:
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return False, None, f"API 서버에 접속하지 못했습니다. (오류 내용: {e})"

    try:
        data = response.json()
    except ValueError:
        return False, None, "서버 응답을 해석할 수 없습니다. (JSON 형식이 아닙니다)"

    if "faultInfo" in data:
        fault = data["faultInfo"]
        message = fault.get("message", "알 수 없는 오류가 발생했습니다.")
        return False, None, f"API 요청이 실패했습니다. 안내 메시지: {message}"

    if "RESULT" in data:
        result = data["RESULT"]
        code = result.get("CODE", "UNKNOWN")
        message = result.get("MESSAGE", "알 수 없는 오류가 발생했습니다.")
        return False, None, f"API 요청이 실패했습니다. ({code}) {message}"

    service_key = "RealtimeCityAir"
    if service_key not in data:
        return False, None, "API 응답 형식이 예상과 달라 데이터를 읽을 수 없습니다."

    service_data = data[service_key]
    inner_result = service_data.get("RESULT", {})
    inner_code = inner_result.get("CODE", "")
    inner_message = inner_result.get("MESSAGE", "")

    if inner_code and inner_code != "INFO-000":
        return False, None, f"API 요청이 실패했습니다. ({inner_code}) {inner_message}"

    row_list = service_data.get("row", [])
    if not row_list:
        return False, None, "조회 조건에 해당하는 데이터가 없습니다."

    df = pd.DataFrame(row_list)
    return True, df, None


# -------------------------------------------------------------------
# 4. 숫자 변환 및 요약 함수
# -------------------------------------------------------------------
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
    summary = summary.merge(station_counts, on="SAREA_NM", how="left")
    return summary


# -------------------------------------------------------------------
# 5. 사이드바 (검색 조건 입력)
# -------------------------------------------------------------------
st.sidebar.header("🔍 조회 조건")

api_key = st.secrets.get("SEOUL_KEY", None)
selected_sarea = st.sidebar.selectbox("권역 선택", SAREA_LIST, index=0)
start_index = st.sidebar.number_input("요청 시작 위치", min_value=1, value=1, step=1)
end_index = st.sidebar.number_input("요청 종료 위치", min_value=1, value=25, step=1)
refresh_clicked = st.sidebar.button("🔄 새로고침(다시 조회)", use_container_width=True)

st.sidebar.caption(f"현재 한국 시간(KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")

# -------------------------------------------------------------------
# 6. 메인 화면 제목 영역
# -------------------------------------------------------------------
st.title("🌫️ 서울시 권역별 실시간 대기환경정보 대시보드")
st.caption(
    f"데이터 출처: 서울 열린데이터광장 OpenAPI (RealtimeCityAir) · "
    f"조회 기준 시각(KST): {now_kst.strftime('%Y년 %m월 %d일 %H시 %M분 %S초')}"
)

# -------------------------------------------------------------------
# 7. 예외 및 인증키 체크
# -------------------------------------------------------------------
if not api_key:
    st.error(
        "❌ 인증키를 찾을 수 없습니다.\n\n"
        "Streamlit Cloud의 **Settings → Secrets** 메뉴에서 `SEOUL_KEY`를 설정해 주세요."
    )
    st.stop()

if end_index < start_index:
    st.warning("⚠️ 요청 종료 위치는 시작 위치보다 크거나 같아야 합니다.")
    st.stop()

if refresh_clicked:
    fetch_realtime_city_air.clear()

# -------------------------------------------------------------------
# 8. API 호출 및 데이터 준비
# -------------------------------------------------------------------
with st.spinner("대기환경 데이터를 불러오는 중입니다..."):
    success, raw_df, error_message = fetch_realtime_city_air(
        api_key=api_key,
        start_index=int(start_index),
        end_index=int(end_index),
        sarea_nm=selected_sarea,
    )

if not success:
    st.error(f"⚠️ 데이터를 불러오지 못했습니다.\n\n{error_message}")
    st.stop()

df = convert_numeric_columns(raw_df)

# ===================================================================
# 9. 탭(Tab) 생성: [📊 대시보드 & 지도] vs [🏃 위치별 맞춤 행동 지침]
# ===================================================================
tab1, tab2 = st.tabs(["📊 대시보드 & 지도", "🏃 위치별 맞춤 행동 지침"])

# -------------------------------------------------------------------
# TAB 1: 기존 메인 대시보드 & 지도
# -------------------------------------------------------------------
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
        region_summary_display = region_summary_df.rename(columns=COLUMN_NAME_MAP)
        if "통합대기환경지수" in region_summary_display.columns:
            region_summary_display = region_summary_display.sort_values(
                by="통합대기환경지수", ascending=False, na_position="last"
            )
        numeric_display_cols = [c for c in region_summary_display.columns if c not in ["권역명", "측정소 개수"]]
        region_summary_display[numeric_display_cols] = region_summary_display[numeric_display_cols].round(3)
        st.dataframe(region_summary_display, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📋 상세표 (측정소별)")
    detail_columns_raw = ["SAREA_NM", "MSRSTN_NM"] + [c for c in DISPLAY_COLUMNS_RAW if c != "SAREA_NM"]
    detail_columns = [c for c in detail_columns_raw if c in df.columns]
    detail_table_df = df[detail_columns].copy().rename(columns=COLUMN_NAME_MAP)

    if "통합대기환경지수" in detail_table_df.columns:
        detail_table_df = detail_table_df.sort_values(by="통합대기환경지수", ascending=False, na_position="last")
    st.dataframe(detail_table_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("🗺️ 서울시 권역별 통합대기환경지수 지도")
    geo_success, geo_data, geo_error = load_seoul_geojson()

    if geo_success and not region_summary_df.empty and "CAI_IDX" in region_summary_df.columns:
        gu_map_df = build_gu_level_map_df(region_summary_df)
        if not gu_map_df.empty:
            common_kwargs = dict(
                data_frame=gu_map_df,
                geojson=geo_data,
                locations="GU_NM",
                featureidkey="properties.name",
                color="CAI_IDX",
                color_continuous_scale="YlOrRd",
                range_color=(0, max(100, gu_map_df["CAI_IDX"].max())),
                zoom=9.3,
                center={"lat": 37.5502, "lon": 126.982},
                opacity=0.75,
                hover_name="GU_NM",
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
            chart_df = df[["MSRSTN_NM", "CAI_IDX"]].dropna().sort_values(by="CAI_IDX", ascending=False)
            st.bar_chart(chart_df.set_index("MSRSTN_NM"))

    with col_g2:
        st.subheader("📈 미세먼지 vs 초미세먼지")
        if "MSRSTN_NM" in df.columns and "PM" in df.columns and "FPM" in df.columns:
            dust_df = df[["MSRSTN_NM", "PM", "FPM"]].dropna().set_index("MSRSTN_NM")
            dust_df = dust_df.rename(columns={"PM": "미세먼지", "FPM": "초미세먼지"})
            st.bar_chart(dust_df)

    with st.expander("🕒 측정일시 포함 원본 데이터 전체 보기"):
        full_columns = [c for c in COLUMN_NAME_MAP.keys() if c in df.columns]
        st.dataframe(df[full_columns].rename(columns=COLUMN_NAME_MAP), use_container_width=True, hide_index=True)


# -------------------------------------------------------------------
# TAB 2: 위치별 실시간 맞춤 행동 지침 (NEW ✨)
# -------------------------------------------------------------------
with tab2:
    st.subheader("📍 내 지역 실시간 대기지수 & 맞춤 행동 수칙")
    st.write("선택하신 위치의 **실시간 측정 수치**를 바탕으로 필요한 수칙을 추천해 드립니다.")

    # 1) 측정소(자치구) 목록 추출
    if "MSRSTN_NM" in df.columns and not df.empty:
        station_list = sorted(df["MSRSTN_NM"].unique().tolist())
        selected_station = st.selectbox("🎯 측정소(자치구)를 선택하세요:", station_list, index=0)

        # 선택한 측정소 데이터 추출
        target_data = df[df["MSRSTN_NM"] == selected_station].iloc[0]

        curr_sarea = target_data.get("SAREA_NM", "-")
        curr_pm = target_data.get("PM", np.nan)
        curr_fpm = target_data.get("FPM", np.nan)
        curr_ozon = target_data.get("OZON", np.nan)
        curr_cai = target_data.get("CAI_IDX", np.nan)
        curr_grd = target_data.get("CAI_GRD", "정보없음")

        st.markdown(f"### 🏢 [{selected_station}] ({curr_sarea}) 실시간 대기 상태")

        # 실시간 주요 지표 카드
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("미세먼지(PM10)", f"{curr_pm} ㎍/㎥" if pd.notnull(curr_pm) else "-")
        c2.metric("초미세먼지(PM2.5)", f"{curr_fpm} ㎍/㎥" if pd.notnull(curr_fpm) else "-")
        c3.metric("오존(O₃)", f"{curr_ozon:.3f} ppm" if pd.notnull(curr_ozon) else "-")
        c4.metric("통합대기지수", f"{curr_cai:.0f}" if pd.notnull(curr_cai) else "-", delta=curr_grd)

        st.markdown("---")
        st.subheader("📋 실시간 추천 액션 플랜 (Action Plan)")

        # ---------------------------------------------------------------
        # [수칙 1] 미세먼지 & 마스크 착용 수칙
        # ---------------------------------------------------------------
        st.markdown("#### 😷 1. 마스크 착용 수칙")
        if pd.notnull(curr_pm) and curr_pm > 80 or (pd.notnull(curr_fpm) and curr_fpm > 35):
            st.error(
                "🚨 **[경고] 미세먼지/초미세먼지 '나쁨' 이상!**\n\n"
                "- 외출 시 **KF94 또는 KF80 보건용 마스크**를 반드시 착용하세요.\n"
                "- 노약자, 임산부, 호흡기 질환자는 장시간 야외 활동을 자제하세요.\n"
                "- 외출 후에는 손, 얼굴을 깨끗이 씻고 수분을 충분히 섭취하세요."
            )
        elif pd.notnull(curr_pm) and curr_pm > 30 or (pd.notnull(curr_fpm) and curr_fpm > 15):
            st.warning(
                "🟡 **[주의] 미세먼지/초미세먼지 '보통' 수준**\n\n"
                "- 민감군(호흡기 질환자, 어린이)은 장시간 야외활동 시 **비말차단/일반 마스크** 착용을 권장합니다.\n"
                "- 일반인은 일상적인 야외활동이 가능합니다."
            )
        else:
            st.success(
                "🟢 **[쾌적] 공기 상태 '좋음'!**\n\n"
                "- 마스크 없이 자유롭게 야외 활동을 즐기셔도 좋습니다."
            )

        # ---------------------------------------------------------------
        # [수칙 2] 실내 환기 수칙
        # ---------------------------------------------------------------
        st.markdown("#### 🪟 2. 실내 환기 수칙")
        if pd.notnull(curr_pm) and curr_pm > 150:
            st.error("❌ **[환기 자제]** 대기 오염이 심각하므로 창문을 닫고 공기청정기를 가동하세요.")
        elif pd.notnull(curr_pm) and curr_pm > 80:
            st.warning("⚠️ **[짧은 환기]** 환기가 꼭 필요하다면 3~5분 이내로 짧게 마친 후 청정기를 틀어주세요.")
        else:
            st.success("✨ **[환기 추천]** 공기가 깨끗합니다! 맞바람이 통하도록 10분 이상 실내 환기를 시켜주세요.")

        # ---------------------------------------------------------------
        # [수칙 3] 오존 & 햇빛/자외선 차단 수칙
        # ---------------------------------------------------------------
        st.markdown("#### ☀️ 3. 오존 및 자외선/선크림 차단 수칙")
        if pd.notnull(curr_ozon) and curr_ozon >= 0.091:
            st.error(
                "🔴 **[오존 주의] 오존 농도가 높습니다!**\n\n"
                "- 오존은 마스크로 걸러지지 않으므로 **오후 2시~5시 사이 야외활동을 자제**하세요.\n"
                "- 외출 시 **SPF30+ 자외선 차단제(선크림)**를 바르고, 모자나 양산을 챙기세요."
            )
        elif pd.notnull(curr_ozon) and curr_ozon >= 0.031:
            st.info(
                "🧴 **[선크림 권장]** 햇볕이 드는 야외 활동 시 **자외선 차단제(선크림)**를 발라 피부를 보호하세요."
            )
        else:
            st.success("🟢 **[오존 안전]** 오존 수치가 안정적입니다.")

        # ---------------------------------------------------------------
        # [수칙 4] 야외 운동 및 산책 권장도
        # ---------------------------------------------------------------
        st.markdown("#### 🏃 4. 야외 운동 및 조깅 권장도")
        if pd.notnull(curr_cai) and curr_cai > 100:
            st.error("🚫 **[실외 운동 비추천]** 헬스장, 실내 체육관 등 **실내 운동**으로 대체하세요.")
        else:
            st.success("🏃‍♂️ **[야외 운동 추천]** 야외 산책이나 조깅을 하기에 무리가 없는 좋은 날씨입니다.")

    else:
        st.info("측정소 데이터를 불러올 수 없습니다. 사이드바의 조회 조건을 확인해 주세요.")

st.caption("본 데이터 및 행동 지침은 참고용이며, 정확한 상황은 환경부 및 서울시 공식 발표를 확인해 주세요.")
