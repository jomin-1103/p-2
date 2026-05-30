"""환경변수 기반 설정 로딩."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    # PostgreSQL
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = _int("DB_PORT", 5432)
    db_name: str = os.getenv("DB_NAME", "ragdb")
    db_user: str = os.getenv("DB_USER", "raguser")
    db_password: str = os.getenv("DB_PASSWORD", "ragpass")

    # Ollama
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    embed_model: str = os.getenv("EMBED_MODEL", "bge-m3")
    llm_model: str = os.getenv("LLM_MODEL", "qwen2.5")
    embed_dim: int = _int("EMBED_DIM", 1024)

    # 청킹 / 검색
    chunk_size: int = _int("CHUNK_SIZE", 800)
    chunk_overlap: int = _int("CHUNK_OVERLAP", 150)
    top_k: int = _int("TOP_K", 5)

    @property
    def dsn(self) -> dict:
        return {
            "host": self.db_host,
            "port": self.db_port,
            "dbname": self.db_name,
            "user": self.db_user,
            "password": self.db_password,
        }


settings = Settings()


# ── 정보보안산업기사 과목 구성 ──────────────────────────────
# 실제 시행 회차/구성에 맞게 자유롭게 수정하세요. (키: 과목 번호)
SUBJECTS: dict[int, str] = {
    1: "시스템 보안",
    2: "네트워크 보안",
    3: "애플리케이션 보안",
    4: "정보보안 일반",
    5: "정보보안 관리 및 법규",
}

# 과목당 문항 수 (질문 번호로 과목을 추정할 때 사용)
QUESTIONS_PER_SUBJECT: int = _int("QUESTIONS_PER_SUBJECT", 20)


def subject_name(no: int) -> str:
    return SUBJECTS.get(no, f"{no}과목")
