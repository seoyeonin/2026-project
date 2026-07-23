# -*- coding: utf-8 -*-
"""
환경 지표 설명 스트림릿 앱
--------------------------------
이 앱은 '지표 설명' 버튼을 누르면, 사용자가 어려운 환경 용어
(예: 이황산가스농도, 이산화탄소농도 등)를 선택했을 때
Solar API(업스테이지)를 이용해서 쉬운 설명과 호흡기 건강 영향을
자동으로 알려주는 프로그램입니다.

- 초보자도 이해할 수 있도록 코드 곳곳에 한국어 주석을 달아두었습니다.
- 스트림릿 클라우드(Streamlit Cloud)에 배포할 것을 가정하고 작성했습니다.
- API 키는 코드에 직접 적지 않고, Streamlit의 "secrets" 기능을 통해
  안전하게 불러옵니다. (설정 방법은 아래 안내 주석 참고)
"""

# ------------------------------------------------------
# 1. 필요한 라이브러리 불러오기
# ------------------------------------------------------
import streamlit as st          # 웹 화면(UI)을 만드는 라이브러리
from openai import OpenAI       # OpenAI 형식의 API를 호출하기 위한 라이브러리
                                 # (Solar API도 OpenAI와 동일한 형식을 지원하므로 이 라이브러리를 그대로 사용합니다)


# ------------------------------------------------------
# 2. 기본 화면 설정
# ------------------------------------------------------
st.set_page_config(
    page_title="환경 지표 설명 도우미",
    page_icon="🌎",
    layout="centered",
)

st.title("🌎 환경 지표 설명 도우미")
st.write(
    "미세먼지, 이산화탄소농도 같은 어려운 환경 용어를 "
    "누구나 쉽게 이해할 수 있도록 설명해 드려요."
)


# ------------------------------------------------------
# 3. Solar API 클라이언트 만들기
# ------------------------------------------------------
# Streamlit Cloud에 배포할 때는 앱 설정(Settings) > Secrets 메뉴에서
# 아래처럼 SOLAR_API_KEY 값을 등록해두어야 합니다.
#
#   SOLAR_API_KEY = "여기에_발급받은_키_입력"
#
# 로컬(내 컴퓨터)에서 테스트할 때는 프로젝트 폴더에
# .streamlit/secrets.toml 파일을 만들고 위와 같은 내용을 넣으면 됩니다.
def get_solar_client():
    """
    Solar API에 접속하기 위한 클라이언트 객체를 만들어 반환하는 함수.
    API 키가 없으면 None을 반환합니다.
    """
    try:
        api_key = st.secrets["SOLAR_API_KEY"]
    except Exception:
        # secrets에 키가 등록되어 있지 않은 경우
        return None

    # OpenAI 라이브러리를 사용하되, 접속 주소(base_url)만 Solar API 주소로 바꿔줍니다.
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.upstage.ai/v1",
    )
    return client


# ------------------------------------------------------
# 4. 환경 용어 목록 (여기서 원하는 용어를 추가/수정할 수 있어요)
# ------------------------------------------------------
ENV_TERMS = [
    "이산화황(아황산가스)농도",
    "이산화질소농도",
    "이산화탄소농도",
    "일산화탄소농도",
    "오존농도",
    "초미세먼지(PM2.5)",
    "미세먼지(PM10)",
    "통합대기환경지수(CAI)",
]


# ------------------------------------------------------
# 5. Solar API를 호출해서 용어 설명을 받아오는 함수
# ------------------------------------------------------
def explain_term(client, term: str) -> str:
    """
    선택한 환경 용어(term)를 Solar API에 보내서
    비전공자도 이해하기 쉬운 설명과 호흡기 건강 영향을 받아오는 함수.

    성공하면: 설명 문자열을 반환
    실패하면: None을 반환 (오류 발생 시 상위 코드에서 안내 메시지를 보여줌)
    """
    # AI에게 어떤 역할을 해야 하는지 알려주는 지시문(프롬프트)입니다.
    system_prompt = (
        "너는 환경 용어를 아주 쉽게 설명해주는 친절한 선생님이야. "
        "전공 지식이 없는 일반인도 이해할 수 있도록 어려운 전문 용어는 "
        "쉬운 말로 풀어서 설명해줘. "
        "답변은 반드시 아래 두 부분으로 나눠서 작성해줘.\n\n"
        "1) 쉬운 정의: 이 용어가 무엇인지 비유나 일상적인 표현을 사용해서 설명\n"
        "2) 호흡기 건강에 미치는 영향: 우리 몸(특히 호흡기)에 어떤 영향을 주는지 설명\n\n"
        "전문 용어를 쓸 때는 반드시 쉬운 말을 함께 덧붙여줘. "
        "답변은 한국어로, 친절하고 부드러운 말투로 작성해줘."
    )

    user_prompt = f"'{term}'에 대해 설명해줘."

    try:
        response = client.chat.completions.create(
            model="solar-open2",  # 모델 이름은 반드시 이 문자열 그대로 사용
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            reasoning_effort="none",  # 추론(생각) 기능 끄기
        )
        # AI가 만든 답변 텍스트를 꺼내옵니다.
        answer = response.choices[0].message.content
        return answer

    except Exception as e:
        # API 호출 중 어떤 이유로든 오류가 발생하면 None을 반환합니다.
        # (예: 인터넷 연결 문제, API 키 오류, 서버 오류 등)
        return None


# ------------------------------------------------------
# 6. 화면(UI) 구성
# ------------------------------------------------------

# 버튼을 누르기 전까지는 설명 영역이 보이지 않도록,
# 세션 상태(session_state)를 이용해서 버튼이 눌렸는지 기억합니다.
if "show_explainer" not in st.session_state:
    st.session_state.show_explainer = False

# '지표 설명' 버튼
if st.button("📘 지표 설명"):
    st.session_state.show_explainer = True

# 버튼이 눌린 상태라면, 용어 선택 화면을 보여줍니다.
if st.session_state.show_explainer:
    st.subheader("궁금한 환경 용어를 선택해 주세요")

    selected_term = st.selectbox(
        "환경 지표 선택",
        ENV_TERMS,
        index=None,
        placeholder="용어를 선택하세요",
    )

    # 사용자가 용어를 하나 선택했을 때만 아래 로직을 실행합니다.
    if selected_term:
        # 먼저 Solar API 클라이언트를 준비합니다.
        client = get_solar_client()

        if client is None:
            # API 키 자체가 없는 경우 (secrets 설정 누락)
            st.error(
                "🙏 죄송해요, 지금은 설명을 불러올 수 없어요.\n\n"
                "앱 설정에 AI 서비스 접속 정보(API 키)가 등록되어 있지 않은 것 같아요. "
                "관리자에게 문의해 주세요."
            )
        else:
            # 로딩 중이라는 것을 사용자에게 보여주기 위한 스피너
            with st.spinner(f"'{selected_term}' 설명을 불러오는 중이에요..."):
                explanation = explain_term(client, selected_term)

            if explanation:
                # 설명을 성공적으로 받아온 경우
                st.success(f"✅ '{selected_term}' 설명이에요!")
                st.markdown(explanation)
            else:
                # 설명 생성에 실패한 경우 -> 친절한 한국어 안내 메시지 표시
                st.error(
                    "🙏 죄송해요, 지금은 설명을 가져오지 못했어요.\n\n"
                    "인터넷 연결 상태를 확인하시거나, 잠시 후 다시 시도해 주세요. "
                    "문제가 계속되면 관리자에게 문의해 주세요."
                )

st.divider()
st.caption(
    "ℹ️ 이 앱은 Solar API(업스테이지)를 이용해 환경 용어를 쉽게 설명해 드립니다. "
    "AI가 생성한 설명이므로 정확한 수치나 기준은 관련 공식 자료를 함께 참고해 주세요."
)
