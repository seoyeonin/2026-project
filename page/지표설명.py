# -*- coding: utf-8 -*-
"""
지표 설명 챗봇 대시보드
- 사용자가 어려운 환경 용어(이산화질소, 오존 등)를 선택하면
  Upstage Solar API(solar-open2)가 비전공자용 설명 + 건강 영향을 알려줍니다.
- Streamlit Cloud 배포를 전제로 작성했습니다.
"""

import streamlit as st   # 웹 대시보드 UI 라이브러리
from openai import OpenAI  # Solar API가 OpenAI 호환 규격이라 openai 패키지를 그대로 사용

# -------------------------------------------------------------------
# 0. 페이지 기본 설정
# -------------------------------------------------------------------
st.set_page_config(
    page_title="대기환경 지표 설명 도우미",
    page_icon="📘",
    layout="centered",
)

# -------------------------------------------------------------------
# 1. 설명이 필요한 환경 용어 목록
# -------------------------------------------------------------------
# 화면에 보여줄 한글 용어와, 실제로 AI에게 보낼 때 쓸 정식 명칭을 함께 관리합니다.
TERM_LIST = [
    "미세먼지(PM10)",
    "초미세먼지(PM2.5)",
    "오존(O3)",
    "이산화질소농도(NO2)",
    "일산화탄소농도(CO)",
    "아황산가스농도(SO2)",
    "통합대기환경지수(CAI)",
]

# -------------------------------------------------------------------
# 2. Solar API 클라이언트 준비
# -------------------------------------------------------------------
# secrets.toml(또는 Streamlit Cloud의 Secrets 설정)에서 인증키를 불러옵니다.
# 코드에는 절대로 실제 키 값을 직접 적지 않습니다.
solar_api_key = st.secrets.get("SOLAR_API_KEY", None)

# openai 라이브러리는 OpenAI 서버가 아니어도, base_url만 바꿔주면
# 같은 방식으로 Solar API(업스테이지)를 호출할 수 있습니다.
client = None
if solar_api_key:
    client = OpenAI(
        api_key=solar_api_key,
        base_url="https://api.upstage.ai/v1",
    )


# -------------------------------------------------------------------
# 3. 용어 설명을 요청하는 함수
# -------------------------------------------------------------------
def explain_term(term: str):
    """
    선택한 환경 용어를 Solar API에 보내서
    (성공여부, 설명글 또는 None, 에러메시지 또는 None) 형태로 돌려주는 함수입니다.
    """
    # 비전공자도 이해하기 쉽게, 그리고 호흡기 건강 영향까지 포함하도록
    # 프롬프트(지시문)를 구체적으로 작성합니다.
    system_prompt = (
        "너는 환경 보건 분야를 쉽게 설명해주는 한국어 도우미야. "
        "전문 용어를 모르는 일반인도 이해할 수 있도록, 어려운 화학·의학 용어는 "
        "최대한 풀어서 설명해줘. 답변은 아래 두 부분으로 구성해줘.\n"
        "1) 이게 뭔가요? : 이 물질/지표가 무엇인지 쉬운 비유를 들어 3~4문장으로 설명\n"
        "2) 호흡기 건강에 미치는 영향 : 이 물질이 우리 몸, 특히 호흡기(폐, 기관지 등)에 "
        "어떤 영향을 주는지 3~4문장으로 설명\n"
        "전문용어를 쓸 때는 반드시 옆에 쉬운 말로 괄호 설명을 덧붙여줘."
    )
    user_prompt = f"'{term}'에 대해 설명해줘."

    try:
        response = client.chat.completions.create(
            model="solar-open2",  # 모델 이름은 요청대로 글자 그대로 사용
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            # 추론(생각) 기능을 끄기 위한 옵션입니다.
            # solar-open2는 기본적으로 추론 기능이 있는 모델이라
            # reasoning_effort를 "none"으로 지정해 답변 속도를 높이고 단순 설명에 집중하게 합니다.
            reasoning_effort="none",
        )
    except Exception as e:
        # 네트워크 오류, 인증키 오류, 서버 오류 등 모든 실패 상황을 여기서 처리합니다.
        return False, None, f"AI 설명을 가져오는 데 실패했습니다. (오류 내용: {e})"

    try:
        answer = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        return False, None, "AI 응답 형식이 예상과 달라 설명을 읽을 수 없습니다."

    if not answer or not answer.strip():
        return False, None, "AI가 빈 답변을 보냈습니다. 잠시 후 다시 시도해주세요."

    return True, answer, None


# -------------------------------------------------------------------
# 4. 화면 구성
# -------------------------------------------------------------------
st.title("📘 대기환경 지표 설명 도우미")
st.caption("어려운 환경 용어를 골라주시면, 쉬운 말로 풀어서 설명해드립니다.")

# 세션 상태(session_state)에 "지표 설명 창을 열지 말지" 값을 저장해둡니다.
# 이렇게 해야 버튼을 눌러도 페이지가 새로고침되면서 설명창이 사라지지 않습니다.
if "show_explainer" not in st.session_state:
    st.session_state.show_explainer = False

# -------------------------------------------------------------------
# 5. '지표 설명' 버튼
# -------------------------------------------------------------------
if st.button("📖 지표 설명", use_container_width=True):
    st.session_state.show_explainer = True

# -------------------------------------------------------------------
# 6. 버튼을 눌렀을 때만 아래 설명 UI를 보여줍니다.
# -------------------------------------------------------------------
if st.session_state.show_explainer:
    st.divider()
    st.subheader("어떤 용어가 궁금하신가요?")

    # 인증키가 없으면, 여기서 바로 안내하고 이후 로직을 실행하지 않습니다.
    if not solar_api_key:
        st.error(
            "❌ Solar API 인증키를 찾을 수 없습니다.\n\n"
            "Streamlit Cloud의 **Settings → Secrets** 메뉴에서 아래와 같이 추가해주세요.\n\n"
            "```toml\n"
            'SOLAR_API_KEY = "발급받은_인증키"\n'
            "```"
        )
    else:
        selected_term = st.selectbox("설명이 필요한 용어를 선택하세요", TERM_LIST)

        if st.button("이 용어 설명 보기"):
            with st.spinner(f"'{selected_term}'에 대해 AI가 쉽게 설명을 준비하고 있습니다..."):
                success, explanation, error_message = explain_term(selected_term)

            if success:
                st.success(f"✅ '{selected_term}' 설명")
                st.markdown(explanation)
            else:
                # 요약(설명) 실패 시 친절한 한국어 안내
                st.error(f"⚠️ 설명을 가져오지 못했습니다.\n\n{error_message}")
                st.info(
                    "💡 확인해보세요\n"
                    "- Solar API 인증키가 올바르게 등록되어 있는지\n"
                    "- 인터넷 연결 상태가 정상인지\n"
                    "- 잠시 후 다시 시도했을 때도 같은 문제가 반복되는지"
                )

st.divider()
st.caption(
    "본 설명은 AI가 생성한 일반 정보이며, 의학적 진단이나 처방을 대체하지 않습니다. "
    "건강에 이상이 느껴지면 반드시 의료 전문가와 상담해주세요."
)
