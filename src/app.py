"""Streamlit 기반 정보보안산업기사 기출 RAG 챗봇 (ChatGPT 스타일 UI).

실행:
    streamlit run streamlit_app.py
"""
from __future__ import annotations

from uuid import uuid4

import streamlit as st

from . import config, db, rag
from .config import settings

st.set_page_config(
    page_title="정보보안산업기사 기출 챗봇",
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="expanded",
)

USER_AVATAR = "🧑"
BOT_AVATAR = "🔐"

# ── ChatGPT 풍 스타일 ─────────────────────────────────────────
_CSS = """
<style>
#MainMenu, header, footer {visibility: hidden;}
.block-container {max-width: 768px; padding-top: 2.2rem; padding-bottom: 7rem;}

/* 메시지 영역: 배경 제거, 줄간격 여유 */
[data-testid="stChatMessage"] {
    background: transparent;
    padding: .35rem 0;
}
[data-testid="stChatMessageContent"] p {line-height: 1.7;}

/* 하단 입력창 중앙 정렬 */
[data-testid="stBottomBlockContainer"] {max-width: 768px; margin: 0 auto;}
[data-testid="stChatInput"] textarea {font-size: 1rem;}

/* 문제 카드 */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px;
}

/* 사이드바 대화목록 버튼 */
section[data-testid="stSidebar"] button {text-align: left;}
</style>
"""


# ── 세션 상태 ─────────────────────────────────────────────────
def _new_chat() -> str:
    cid = str(uuid4())
    st.session_state.chats[cid] = {"title": "새 채팅", "messages": []}
    st.session_state.current = cid
    return cid


def _ensure_state() -> None:
    if "chats" not in st.session_state:
        st.session_state.chats = {}
        st.session_state.current = None
    if not st.session_state.chats or st.session_state.current is None:
        _new_chat()


def _current_messages() -> list[dict]:
    return st.session_state.chats[st.session_state.current]["messages"]


# ── DB 통계 (사이드바) ────────────────────────────────────────
@st.cache_data(ttl=20)
def _load_stats():
    try:
        with db.connection() as conn:
            return db.count_chunks(conn), db.list_sources(conn), db.list_years(conn), None
    except Exception as e:
        return None, None, None, str(e)


# ── 사이드바 ──────────────────────────────────────────────────
def sidebar() -> str:
    with st.sidebar:
        if st.button("➕ 새 채팅", use_container_width=True):
            _new_chat()
            st.rerun()

        st.markdown("##### 대화 목록")
        for cid, chat in reversed(list(st.session_state.chats.items())):
            label = chat["title"] if chat["title"] else "새 채팅"
            is_cur = cid == st.session_state.current
            if st.button(("🟢 " if is_cur else "💬 ") + label[:24],
                         key=f"chat_{cid}", use_container_width=True):
                st.session_state.current = cid
                st.rerun()

        st.divider()
        mode = st.selectbox(
            "응답 모드 (일반 질문용)",
            options=list(rag.MODE_LABELS.keys()),
            format_func=lambda k: rag.MODE_LABELS[k],
        )

        st.divider()
        st.markdown("##### 📚 적재 현황")
        total, sources, years, err = _load_stats()
        if err:
            st.error("DB 연결 실패")
            st.caption(err)
        elif not total:
            st.warning("적재된 자료가 없습니다.\n`python -m src.ingest` 실행")
        else:
            st.caption(f"총 {total:,}개 청크")
            if years:
                st.caption("연도: " + ", ".join(str(y) for y in years))
            with st.expander(f"파일 {len(sources)}건"):
                for s in sources:
                    st.write(f"• {s['source']} ({s['chunks']})")

        st.divider()
        st.caption(f"임베딩 `{settings.embed_model}` · LLM `{settings.llm_model}`")
        st.caption('💡 팁: **"21년도 1과목"** 처럼 입력하면 과목별 문제·선지·해설을 정리해 드려요.')
    return mode


# ── 렌더링 ────────────────────────────────────────────────────
def _render_sources(sources: list[dict]) -> None:
    if not sources:
        return
    with st.expander(f"📎 참고한 자료 {len(sources)}건"):
        for i, s in enumerate(sources, start=1):
            loc = f"{s['source']} p.{s['page']}" if s.get("page") else s["source"]
            st.markdown(f"**[{i}] {loc}**"
                        + (f" · 유사도 {s['score']:.3f}" if s.get("score") is not None else ""))
            st.caption(s["content"][:300] + ("..." if len(s["content"]) > 300 else ""))


def _render_exam(msg: dict) -> None:
    sname = config.subject_name(msg["subject"])
    st.markdown(f"### 📘 {msg['year']}년도 정보보안산업기사 "
                f"{msg['subject']}과목 — {sname}")
    questions = msg.get("questions", [])
    if not questions:
        st.warning(
            "해당 연도·과목의 문제를 찾지 못했습니다.\n\n"
            "- 기출 PDF가 적재되어 있는지 (사이드바 적재 현황)\n"
            "- 적재 시 연도/과목 태깅이 되었는지 확인해 주세요.\n"
            "  (연도는 파일명, 과목은 'N과목' 헤더로 인식합니다.)"
        )
        return
    st.caption(f"총 {len(questions)}문제")
    for q in questions:
        with st.container(border=True):
            st.markdown(f"**문제 {q.get('number', '?')}.** {q.get('question', '')}")
            for c in q.get("choices", []) or []:
                st.markdown(f"&nbsp;&nbsp;{c}", unsafe_allow_html=True)
            if q.get("answer"):
                st.markdown(f"✅ **정답:** {q['answer']}")
            if q.get("explanation"):
                st.info(f"**해설** · {q['explanation']}")
    _render_sources(msg.get("sources", []))


def _render_message(msg: dict) -> None:
    avatar = USER_AVATAR if msg["role"] == "user" else BOT_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
        if msg.get("kind") == "exam":
            _render_exam(msg)
        else:
            st.markdown(msg["content"])
            _render_sources(msg.get("sources", []))


# ── 메인 ──────────────────────────────────────────────────────
def main() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    _ensure_state()
    mode = sidebar()

    messages = _current_messages()

    if not messages:
        st.markdown("<div style='text-align:center; margin-top:3rem;'>"
                    "<h2>🔐 정보보안산업기사 기출 챗봇</h2>"
                    "<p style='color:#888;'>무엇을 도와드릴까요? "
                    "예) <code>21년도 1과목</code>, <code>SQL 인젝션 방어 기법 설명해줘</code></p>"
                    "</div>", unsafe_allow_html=True)

    for msg in messages:
        _render_message(msg)

    prompt = st.chat_input("질문이나 요청을 입력하세요  (예: 21년도 1과목)")
    if not prompt:
        return

    # 첫 메시지면 대화 제목 갱신
    chat = st.session_state.chats[st.session_state.current]
    if chat["title"] == "새 채팅":
        chat["title"] = prompt.strip()[:24]

    user_msg = {"role": "user", "kind": "text", "content": prompt}
    messages.append(user_msg)
    _render_message(user_msg)

    exam_req = rag.parse_exam_request(prompt)

    with st.chat_message("assistant", avatar=BOT_AVATAR):
        if exam_req:
            # ── 구조화 요청: "N년도 M과목" ──
            year, subject = exam_req
            with st.spinner(f"{year}년도 {subject}과목 문제를 정리하는 중..."):
                try:
                    questions, sources = rag.fetch_exam_questions(year, subject)
                    err = None
                except Exception as e:
                    questions, sources, err = [], [], str(e)
            assistant_msg = {
                "role": "assistant", "kind": "exam",
                "year": year, "subject": subject,
                "questions": questions, "sources": sources,
            }
            if err:
                st.error(f"⚠️ 오류가 발생했습니다: {err}")
            else:
                _render_exam(assistant_msg)
        else:
            # ── 일반 RAG 질의응답 ──
            history = [{"role": m["role"], "content": m["content"]}
                       for m in messages[:-1] if m.get("kind") == "text"]
            try:
                gen, sources = rag.generate(prompt, mode=mode, history=history)
                full = st.write_stream(gen)
                _render_sources(sources)
            except Exception as e:
                full, sources = f"⚠️ 오류가 발생했습니다: {e}", []
                st.error(full)
            assistant_msg = {
                "role": "assistant", "kind": "text",
                "content": full, "sources": sources,
            }

    messages.append(assistant_msg)


if __name__ == "__main__":
    main()
