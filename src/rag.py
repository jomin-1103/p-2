"""검색(Retrieval) + Ollama(qwen2.5) 생성(Generation) 엔진.

기본 질의응답(qa) 외에 Ollama 모델이 제공하는 부가 기능 모드:
  - explain : 기출 문제/정답에 대한 상세 해설
  - quiz    : 기출 스타일의 모의 문제 생성
  - summary : 특정 주제/단원 핵심 요약
"""
from __future__ import annotations

import json
import re
from typing import Iterator

import ollama

from . import config, db, embeddings
from .config import settings

_client = ollama.Client(host=settings.ollama_host)

SYSTEM_BASE = (
    "당신은 한국 '정보보안산업기사' 자격증 시험을 돕는 전문 튜터입니다. "
    "아래 <참고자료> 는 실제 기출 PDF 에서 검색된 내용입니다. "
    "답변은 반드시 한국어로 하고, 참고자료에 근거해 정확하게 설명하세요. "
    "참고자료에 없는 내용을 추측해야 한다면 '참고자료에 없는 일반 지식' 임을 분명히 밝히세요."
)

MODE_INSTRUCTIONS = {
    "qa": "사용자의 질문에 핵심을 먼저 답하고, 필요하면 근거와 함께 부연 설명하세요.",
    "explain": (
        "사용자가 제시한 문제 또는 개념을 단계별로 해설하세요. "
        "정답과 그 이유, 오답이 왜 틀렸는지, 관련 핵심 개념을 정리해 설명합니다."
    ),
    "quiz": (
        "참고자료의 주제를 바탕으로 정보보안산업기사 기출 스타일의 객관식 4지선다 "
        "문제 3개를 생성하세요. 각 문제마다 정답과 간단한 해설을 함께 제시합니다."
    ),
    "summary": (
        "사용자가 요청한 주제/단원을 시험 대비용으로 핵심만 간결하게 요약하세요. "
        "중요 용어는 굵게 강조하고, 외워야 할 포인트를 불릿으로 정리합니다."
    ),
}

MODE_LABELS = {
    "qa": "💬 기출 질의응답",
    "explain": "📖 문제·개념 해설",
    "quiz": "📝 모의문제 생성",
    "summary": "🗂️ 핵심 요약",
}


def retrieve(query: str, top_k: int | None = None,
             sources: list[str] | None = None) -> list[dict]:
    """질의를 임베딩해 관련 청크를 검색."""
    emb = embeddings.embed_text(query)
    with db.get_connection() as conn:
        return db.search(conn, emb, top_k or settings.top_k, sources)


def build_context(results: list[dict]) -> str:
    if not results:
        return "(검색된 참고자료가 없습니다.)"
    blocks = []
    for i, r in enumerate(results, start=1):
        loc = f"{r['source']} p.{r['page']}" if r.get("page") else r["source"]
        blocks.append(f"[자료 {i}] (출처: {loc}, 유사도: {r['score']:.3f})\n{r['content']}")
    return "\n\n".join(blocks)


def _build_messages(query: str, mode: str, context: str,
                    history: list[dict] | None) -> list[dict]:
    system = f"{SYSTEM_BASE}\n\n[모드 지시] {MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS['qa'])}"
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    user = f"<참고자료>\n{context}\n</참고자료>\n\n[요청]\n{query}"
    messages.append({"role": "user", "content": user})
    return messages


def generate(query: str, mode: str = "qa",
             history: list[dict] | None = None,
             top_k: int | None = None) -> tuple[Iterator[str], list[dict]]:
    """답변 토큰 스트림 제너레이터와 검색 결과(출처)를 반환."""
    results = retrieve(query, top_k=top_k)
    context = build_context(results)
    messages = _build_messages(query, mode, context, history)

    stream = _client.chat(model=settings.llm_model, messages=messages, stream=True)

    def token_gen() -> Iterator[str]:
        for part in stream:
            yield part["message"]["content"]

    return token_gen(), results


def answer(query: str, mode: str = "qa",
           history: list[dict] | None = None) -> tuple[str, list[dict]]:
    """스트리밍 없이 완성된 답변 문자열과 출처를 반환 (CLI/테스트용)."""
    gen, results = generate(query, mode=mode, history=history)
    return "".join(gen), results


# ─────────────────────────────────────────────────────────────
# 구조화 요청: "21년도 1과목" → 과목별 문제/선지/해설
# ─────────────────────────────────────────────────────────────

# "21년", "2021년도", "13 년" 등에서 연도 / "1과목" 에서 과목 추출
_YEAR_RE = re.compile(r"(?:20)?(\d{2})\s*년")
_SUBJECT_RE = re.compile(r"([1-5])\s*과목")


def parse_exam_request(query: str) -> tuple[int, int] | None:
    """질의에서 (연도, 과목번호) 를 추출. 둘 다 있으면 구조화 요청으로 간주."""
    ym = _YEAR_RE.search(query)
    sm = _SUBJECT_RE.search(query)
    if not (ym and sm):
        return None
    yy = int(ym.group(1))
    year = 2000 + yy if yy < 90 else 1900 + yy
    return year, int(sm.group(1))


_EXAM_SYSTEM = (
    "당신은 한국 '정보보안산업기사' 기출문제를 정리하는 도우미입니다. "
    "제공된 <참고자료> 안에 있는 문제만 사용하고, 자료에 없는 문제를 지어내지 마세요. "
    "반드시 한국어로, 지정한 JSON 형식으로만 응답하세요."
)

_EXAM_SCHEMA = (
    '{"questions": [{"number": 정수, "question": "문제 본문", '
    '"choices": ["①...", "②...", "③...", "④..."], '
    '"answer": "정답 보기", "explanation": "해설"}]}'
)


def fetch_exam_questions(year: int, subject: int) -> tuple[list[dict], list[dict]]:
    """해당 연도·과목의 문제를 구조화해서 반환.

    Returns: (questions, sources)
      - questions: number/question/choices/answer/explanation 딕셔너리 목록
      - sources:   근거로 사용한 청크(출처 표시용)
    """
    with db.connection() as conn:
        rows = db.search_by_meta(conn, year, subject, limit=80)
        if not rows:
            # 메타 태깅이 없을 때를 대비한 의미 검색 폴백
            sname = config.subject_name(subject)
            emb = embeddings.embed_text(f"{year}년 정보보안산업기사 {subject}과목 {sname} 기출문제")
            rows = db.search(conn, emb, top_k=40)

    if not rows:
        return [], []

    sname = config.subject_name(subject)
    context = build_context(rows)
    user = (
        f"다음은 {year}년도 정보보안산업기사 {subject}과목({sname}) 관련 기출 자료입니다.\n"
        f"이 자료에서 {subject}과목에 해당하는 문제를 문제 번호 순서대로 모두 정리하세요.\n"
        "각 문제마다 문제 본문, 선지(보기), 정답, 해설을 채웁니다.\n"
        "- 자료에 해설이 없으면 정답 근거를 바탕으로 간결한 해설을 직접 작성하고, "
        "해설 앞에 '(AI 생성 해설) ' 을 붙이세요.\n"
        "- 정답이 자료에 명시되지 않았으면 가장 타당한 보기를 정답으로 고르고 그 이유를 해설에 적으세요.\n\n"
        f"<참고자료>\n{context}\n</참고자료>\n\n"
        f"아래 JSON 스키마로만 출력하세요:\n{_EXAM_SCHEMA}"
    )

    resp = _client.chat(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": _EXAM_SYSTEM},
            {"role": "user", "content": user},
        ],
        format="json",
    )
    raw = resp["message"]["content"]
    try:
        data = json.loads(raw)
        questions = data.get("questions", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, TypeError):
        questions = []
    return questions, rows
