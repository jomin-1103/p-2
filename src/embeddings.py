"""Ollama 임베딩 모델(bge-m3) 래퍼."""
from __future__ import annotations

from typing import Sequence

import ollama

from .config import settings

_client = ollama.Client(host=settings.ollama_host)


def embed_text(text: str) -> list[float]:
    """단일 텍스트를 임베딩 벡터로 변환."""
    resp = _client.embeddings(model=settings.embed_model, prompt=text)
    return list(resp["embedding"])


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """여러 텍스트를 순차 임베딩."""
    return [embed_text(t) for t in texts]
