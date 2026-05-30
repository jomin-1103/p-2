"""Streamlit 기반 정보보안산업기사 기출 RAG 챗봇.

실행:
    streamlit run src/app.py
"""
from __future__ import annotations

import streamlit as st

from . import db, rag
from .config import settings

st.set_page_config(page_title="정보보안산업기사 기출 RAG 챗봇", page_icon="🔐", layout="wide")


@st.cache_data(ttl=30)
def _load_stats():
    try:
        with db.get_connection() as conn:
            return db.count_chunks(conn), db.list_sources(conn)
    except Exception as e:  # DB 미연결 등
        return None, str(e)


def sidebar() -> str:
    st.sidebar.title("🔐 설정")

    mode = st.sidebar.radio(
        "모드 선택",
        options=list(rag.MODE_LABELS.keys()),
        format_func=lambda k: rag.MODE_LABELS[k],
    )

    st.sidebar.divider()
    st.sidebar.subheader("📚 적재된 기출 자료")
    total, sources = _load_stats()
    if total is None:
        st.sidebar.error(f"DB 연결 실패: {sources}")
        st.sidebar.caption("docker compose up -d 후 python -m src.init_db 를 실행하세요.")
    elif total == 0:
        st.sidebar.warning("적재된 자료가 없습니다.\ndata/pdfs/ 에 PDF 를 넣고\n`python -m src.ingest` 를 실행하세요.")
    else:
        st.sidebar.caption(f"총 {total:,}개 청크")
        for s in sources:
            st.sidebar.write(f"• {s['source']} ({s['chunks']})")

    st.sidebar.divider()
    st.sidebar.caption(f"임베딩: `{settings.embed_model}` · LLM: `{settings.llm_model}`")
    if st.sidebar.button("🗑️ 대화 초기화"):
        st.session_state.messages = []
        st.rerun()

    return mode


def main() -> None:
    mode = sidebar()

    st.title("🔐 정보보안산업기사 기출 RAG 챗봇")
    st.caption(f"현재 모드: {rag.MODE_LABELS[mode]}")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 지난 대화 렌더링
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                _render_sources(msg["sources"])

    prompt = st.chat_input("질문이나 요청을 입력하세요 (예: SQL 인젝션 방어 기법 설명해줘)")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # LLM 에는 source 메타를 제외한 role/content 만 히스토리로 전달
    history = [{"role": m["role"], "content": m["content"]}
               for m in st.session_state.messages[:-1]]

    with st.chat_message("assistant"):
        try:
            gen, sources = rag.generate(prompt, mode=mode, history=history)
            full = st.write_stream(gen)
            _render_sources(sources)
        except Exception as e:
            full = f"⚠️ 오류가 발생했습니다: {e}"
            sources = []
            st.error(full)

    st.session_state.messages.append(
        {"role": "assistant", "content": full, "sources": sources}
    )


def _render_sources(sources: list[dict]) -> None:
    if not sources:
        return
    with st.expander(f"📎 참고한 자료 {len(sources)}건"):
        for i, s in enumerate(sources, start=1):
            loc = f"{s['source']} p.{s['page']}" if s.get("page") else s["source"]
            st.markdown(f"**[{i}] {loc}** · 유사도 {s['score']:.3f}")
            st.caption(s["content"][:300] + ("..." if len(s["content"]) > 300 else ""))


if __name__ == "__main__":
    main()
