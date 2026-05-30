"""검색(Retrieval) + Ollama(qwen2.5) 생성(Generation) 엔진.

기본 질의응답(qa) 외에 Ollama 모델이 제공하는 부가 기능 모드:
  - explain : 기출 문제/정답에 대한 상세 해설
  - quiz    : 기출 스타일의 모의 문제 생성
  - summary : 특정 주제/단원 핵심 요약
"""
from __future__ import annotations

from typing import Iterator

import ollama

from . import db, embeddings
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
