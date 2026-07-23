# -*- coding: utf-8 -*-
"""
서울시 권역별 실시간 대기환경정보 분석 대시보드
- 서울 열린데이터광장 OpenAPI(RealtimeCityAir) 사용
- Streamlit Cloud 배포 전제로 작성
"""

import requests               # API 호출용 라이브러리
import pandas as pd           # 표/데이터 처리용 라이브러리
import numpy as np            # 숫자 계산용 라이브러리
import streamlit as st        # 웹 대시보드 UI 라이브러리
from datetime import datetime # 현재 시각 표시용
from zoneinfo import ZoneInfo # 한국 시간(Asia/Seoul) 계산용 (표준 라이브러리)

# -------------------------------------------------------------------
# 0. 페이지 기본 설정
# -------------------------------------------------------------------
# 브라우저 탭 제목, 아이콘, 화면 레이아웃(넓게)을 지정합니다.
st.set_page_config(
    page_title="서울시 권역별 실시간 대기환경 대시보드",
    page_icon="🌫️",
    layout="wide",
)

# -------------------------------------------------------------------
# 1. 한국 시간(Asia/Seoul) 계산
# -------------------------------------------------------------------
# 배포 서버(스트림릿 클라우드)는 UTC 등 외국 시간대일 수 있으므로,
# 반드시 zoneinfo를 이용해 한국 시간으로 명시적으로 변환해서 사용합니다.
KST = ZoneInfo("Asia/Seoul")
now_kst = datetime.now(KST)

# -------------------------------------------------------------------
# 2. 화면에 쓰일 상수값 정의
# -------------------------------------------------------------------
# 문서에서 안내한 5개 권역명입니다. (선택 파라미터 SAREA_NM에 사용)
SAREA_LIST = ["전체", "도심권", "동북권", "동남권", "서북권", "서남권"]

# 표에 보여줄 컬럼(출력명)과, 화면에 표시할 한글 이름을 매핑합니다.
# API가 내려주는 원래 필드명 -> 사람이 읽기 좋은 한글 이름
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

# 사용자 요청에 따라, 최종적으로 표에 보여줄 컬럼 순서를 지정합니다.
DISPLAY_COLUMNS_RAW = [
    "SAREA_NM", "PM", "FPM", "OZON", "NTDX", "CBMX", "SPDX", "CAI_GRD", "CAI_IDX"
]

# 숫자로 변환해서 다뤄야 하는 컬럼들 (API가 문자열로 내려주기 때문)
NUMERIC_COLUMNS = ["PM", "FPM", "OZON", "NTDX", "CBMX", "SPDX", "CAI_IDX"]


# -------------------------------------------------------------------
# 3. API 호출 함수
# -------------------------------------------------------------------
# st.cache_data를 사용해 같은 조건으로는 5분 동안 재호출하지 않도록 캐싱합니다.
# (API 서버 부담을 줄이고, 앱 반응 속도도 빨라집니다.)
@st.cache_data(ttl=300, show_spinner=False)
def fetch_realtime_city_air(api_key: str, start_index: int, end_index: int, sarea_nm: str = None):
    """
    서울시 실시간 권역별 대기환경 정보를 호출해서
    (성공여부, 데이터프레임 또는 None, 에러메시지 또는 None) 형태로 돌려주는 함수입니다.
    """
    # 서울시 OpenAPI 공통 URL 규칙:
    # http://openapi.seoul.go.kr:8088/{인증키}/{요청타입}/{서비스명}/{시작인덱스}/{종료인덱스}/{선택인자...}
    base_url = (
        f"http://openapi.seoul.go.kr:8088/{api_key}/json/"
        f"RealtimeCityAir/{start_index}/{end_index}/"
    )

    # 선택 파라미터인 권역명(SAREA_NM)이 있으면 URL 뒤에 이어붙입니다.
    # 서울시 OpenAPI는 선택 인자를 경로(path) 형태로 순서대로 붙이는 방식입니다.
    if sarea_nm and sarea_nm != "전체":
        base_url += f"{sarea_nm}/"

    try:
        # timeout을 걸어서, 서버가 응답이 없을 때 무한정 기다리지 않도록 합니다.
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()  # HTTP 오류(404, 500 등)가 나면 예외를 발생시킴
    except requests.exceptions.RequestException as e:
        # 네트워크 오류, 타임아웃, 서버 오류 등 모든 요청 실패를 여기서 처리
        return False, None, f"API 서버에 접속하지 못했습니다. (오류 내용: {e})"

    try:
        data = response.json()
    except ValueError:
        # 응답이 JSON 형식이 아닐 때 (예: HTML 에러 페이지가 온 경우)
        return False, None, "서버 응답을 해석할 수 없습니다. (JSON 형식이 아닙니다)"

    # -----------------------------------------------------------
    # 서울시 OpenAPI는 오류가 나면 최상위 키가 서비스명이 아니라
    # "RESULT" 라는 키로 오류 코드/메시지를 내려주는 경우가 많습니다.
    # 또한 문제에서 언급한 대로 "faultInfo" 형태로 올 수도 있으므로 함께 체크합니다.
    # -----------------------------------------------------------
    if "faultInfo" in data:
        fault = data["faultInfo"]
        message = fault.get("message", "알 수 없는 오류가 발생했습니다.")
        return False, None, f"API 요청이 실패했습니다. 안내 메시지: {message}"

    if "RESULT" in data:
        # 서비스명 키가 아예 없이 RESULT만 온 경우는 대부분 오류 응답입니다.
        result = data["RESULT"]
        code = result.get("CODE", "UNKNOWN")
        message = result.get("MESSAGE", "알 수 없는 오류가 발생했습니다.")
        return False, None, f"API 요청이 실패했습니다. ({code}) {message}"

    # 정상 응답이라면 "RealtimeCityAir" 키 아래에 실제 데이터가 들어 있습니다.
    service_key = "RealtimeCityAir"
    if service_key not in data:
        return False, None, "API 응답 형식이 예상과 달라 데이터를 읽을 수 없습니다."

    service_data = data[service_key]

    # 서비스 데이터 안에도 RESULT.CODE가 있는데, 정상일 때는 보통 "INFO-000" 입니다.
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
# 4. 숫자 변환 함수
# -------------------------------------------------------------------
def convert_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    API에서 문자열로 내려오는 숫자 컬럼들을 실제 숫자(float)로 바꿔줍니다.
    변환할 수 없는 값(빈 문자열, '-' 등)은 결측치(NaN)로 처리합니다.
    """
    df = df.copy()
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            # errors="coerce" : 숫자로 바꿀 수 없는 값은 NaN으로 만들어줌
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# -------------------------------------------------------------------
# 5. 사이드바 (검색 조건 입력)
# -------------------------------------------------------------------
st.sidebar.header("🔍 조회 조건")

# secrets.toml (또는 스트림릿 클라우드의 Secrets 설정)에서 인증키를 불러옵니다.
# 코드에는 절대로 실제 키 값을 직접 적지 않습니다.
api_key = st.secrets.get("SEOUL_KEY", None)

selected_sarea = st.sidebar.selectbox("권역 선택", SAREA_LIST, index=0)

start_index = st.sidebar.number_input("요청 시작 위치", min_value=1, value=1, step=1)
end_index = st.sidebar.number_input("요청 종료 위치", min_value=1, value=25, step=1)

refresh_clicked = st.sidebar.button("🔄 새로고침(다시 조회)", use_container_width=True)

st.sidebar.caption(f"현재 한국 시간(KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")

# -------------------------------------------------------------------
# 6. 메인 화면 제목 영역
# -------------------------------------------------------------------
st.title("🌫️ 서울시 권역별 실시간 대기환경정보 분석 대시보드")
st.caption(
    f"데이터 출처: 서울 열린데이터광장 OpenAPI (RealtimeCityAir) · "
    f"조회 기준 시각(KST): {now_kst.strftime('%Y년 %m월 %d일 %H시 %M분 %S초')}"
)

# -------------------------------------------------------------------
# 7. 인증키가 없을 때 안내
# -------------------------------------------------------------------
if not api_key:
    st.error(
        "❌ 인증키를 찾을 수 없습니다.\n\n"
        "Streamlit Cloud의 **Settings → Secrets** 메뉴에서 아래와 같이 추가해주세요.\n\n"
        "```toml\n"
        'SEOUL_KEY = "발급받은_인증키"\n'
        "```"
    )
    st.stop()  # 인증키가 없으면 이후 코드를 실행하지 않고 여기서 멈춥니다.

# end_index가 start_index보다 작으면 안내 후 중단
if end_index < start_index:
    st.warning("⚠️ 요청 종료 위치는 시작 위치보다 크거나 같아야 합니다. 값을 다시 확인해주세요.")
    st.stop()

# 새로고침 버튼을 누르면 캐시를 비워서 최신 데이터를 다시 받아옵니다.
if refresh_clicked:
    fetch_realtime_city_air.clear()

# -------------------------------------------------------------------
# 8. API 호출 및 결과 처리
# -------------------------------------------------------------------
with st.spinner("대기환경 데이터를 불러오는 중입니다..."):
    success, raw_df, error_message = fetch_realtime_city_air(
        api_key=api_key,
        start_index=int(start_index),
        end_index=int(end_index),
        sarea_nm=selected_sarea,
    )

# 실패했을 때: 친절한 한국어 안내 메시지를 보여주고 앱을 멈춥니다.
if not success:
    st.error(f"⚠️ 데이터를 불러오지 못했습니다.\n\n{error_message}")
    st.info(
        "💡 확인해보세요\n"
        "- 인증키가 올바르게 등록되어 있는지\n"
        "- 요청 시작/종료 위치 값이 올바른지 (예: 1 ~ 25)\n"
        "- 선택한 권역명에 실제로 데이터가 있는지\n"
        "- 서울 열린데이터광장 서버 상태가 정상인지"
    )
    st.stop()

# -------------------------------------------------------------------
# 9. 숫자형 변환 및 표시용 데이터프레임 준비
# -------------------------------------------------------------------
df = convert_numeric_columns(raw_df)

# 화면에 보여줄 컬럼만 순서대로 골라냅니다. (없는 컬럼은 건너뜀)
display_columns = [c for c in DISPLAY_COLUMNS_RAW if c in df.columns]
table_df = df[display_columns].copy()

# 컬럼명을 한글로 바꿔서 보여줍니다.
table_df = table_df.rename(columns=COLUMN_NAME_MAP)

# -------------------------------------------------------------------
# 10. 요약 지표 (전체 평균)
# -------------------------------------------------------------------
st.subheader("📊 요약 지표 (조회 결과 평균)")

col1, col2, col3, col4 = st.columns(4)
col1.metric("평균 미세먼지(㎍/㎥)", f"{df['PM'].mean():.1f}" if "PM" in df.columns else "-")
col2.metric("평균 초미세먼지(㎍/㎥)", f"{df['FPM'].mean():.1f}" if "FPM" in df.columns else "-")
col3.metric("평균 오존(ppm)", f"{df['OZON'].mean():.4f}" if "OZON" in df.columns else "-")
col4.metric("평균 통합대기환경지수", f"{df['CAI_IDX'].mean():.1f}" if "CAI_IDX" in df.columns else "-")

# -------------------------------------------------------------------
# 11. 데이터 표
# -------------------------------------------------------------------
st.subheader("📋 측정소별 상세 데이터")

# 통합대기환경지수(CAI_IDX) 기준으로 정렬해서 보여줍니다. (숫자로 변환되어 있어 정렬이 정확함)
if "통합대기환경지수" in table_df.columns:
    table_df = table_df.sort_values(by="통합대기환경지수", ascending=False, na_position="last")

st.dataframe(table_df, use_container_width=True, hide_index=True)

# -------------------------------------------------------------------
# 12. 그래프: 권역/측정소별 통합대기환경지수 비교
# -------------------------------------------------------------------
st.subheader("📈 측정소별 통합대기환경지수(CAI_IDX) 비교")

if "MSRSTN_NM" in df.columns and "CAI_IDX" in df.columns:
    chart_df = df[["MSRSTN_NM", "CAI_IDX"]].dropna().sort_values(by="CAI_IDX", ascending=False)
    chart_df = chart_df.set_index("MSRSTN_NM")
    st.bar_chart(chart_df)
else:
    st.info("그래프를 그릴 측정소명 또는 통합대기환경지수 데이터가 없습니다.")

# -------------------------------------------------------------------
# 13. 그래프: 미세먼지 vs 초미세먼지 비교
# -------------------------------------------------------------------
st.subheader("📈 측정소별 미세먼지 · 초미세먼지 비교(㎍/㎥)")

if "MSRSTN_NM" in df.columns and "PM" in df.columns and "FPM" in df.columns:
    dust_df = df[["MSRSTN_NM", "PM", "FPM"]].dropna()
    dust_df = dust_df.set_index("MSRSTN_NM")
    dust_df = dust_df.rename(columns={"PM": "미세먼지(㎍/㎥)", "FPM": "초미세먼지(㎍/㎥)"})
    st.bar_chart(dust_df)
else:
    st.info("그래프를 그릴 미세먼지 데이터가 없습니다.")

# -------------------------------------------------------------------
# 14. 통합대기환경등급 분포
# -------------------------------------------------------------------
st.subheader("🏷️ 통합대기환경등급 분포")

if "CAI_GRD" in df.columns:
    grade_counts = df["CAI_GRD"].value_counts().sort_index()
    st.bar_chart(grade_counts)
else:
    st.info("통합대기환경등급 데이터가 없습니다.")

# -------------------------------------------------------------------
# 15. 원본(측정일시 포함) 데이터 펼쳐보기
# -------------------------------------------------------------------
with st.expander("🕒 측정일시 포함 원본 데이터 전체 보기"):
    full_columns = [c for c in COLUMN_NAME_MAP.keys() if c in df.columns]
    full_df = df[full_columns].rename(columns=COLUMN_NAME_MAP)
    st.dataframe(full_df, use_container_width=True, hide_index=True)

st.caption("본 데이터는 참고용이며, 실제 대기환경 판단은 공식 기관의 발표를 따라주세요.")
