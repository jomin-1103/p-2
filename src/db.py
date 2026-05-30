"""PostgreSQL + pgvector 접근 계층.

벡터는 텍스트 리터럴('[a,b,c]')로 전달하고 `::vector` 로 캐스팅하므로
별도의 파이썬 어댑터 등록 없이도 동작합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import psycopg2
from psycopg2.extras import Json, execute_values

from .config import settings

_INIT_SQL = Path(__file__).resolve().parent.parent / "db" / "init.sql"


def get_connection():
    return psycopg2.connect(**settings.dsn)


def _vec_literal(vec: Sequence[float]) -> str:
    """파이썬 시퀀스를 pgvector 입력 리터럴로 변환."""
    return "[" + ",".join(format(float(x), ".8g") for x in vec) + "]"


def init_schema() -> None:
    """db/init.sql 을 실행해 확장/테이블/인덱스를 (멱등하게) 생성."""
    sql = _INIT_SQL.read_text(encoding="utf-8")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)


def delete_source(conn, source: str) -> int:
    """특정 PDF 의 기존 청크를 모두 삭제하고 삭제 건수를 반환."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE source = %s", (source,))
        deleted = cur.rowcount
    conn.commit()
    return deleted


def source_exists(conn, source: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM documents WHERE source = %s LIMIT 1", (source,))
        return cur.fetchone() is not None


def insert_chunks(conn, rows: Iterable[dict]) -> int:
    """청크 행들을 일괄 삽입.

    각 행: {source, page, chunk_index, content, embedding, metadata?}
    """
    rows = list(rows)
    if not rows:
        return 0
    values = [
        (
            r["source"],
            r.get("page"),
            r["chunk_index"],
            r["content"],
            _vec_literal(r["embedding"]),
            Json(r.get("metadata", {})),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO documents
                (source, page, chunk_index, content, embedding, metadata)
            VALUES %s
            """,
            values,
            template="(%s, %s, %s, %s, %s::vector, %s)",
        )
    conn.commit()
    return len(values)


def search(conn, query_embedding: Sequence[float], top_k: int,
           sources: Sequence[str] | None = None) -> list[dict]:
    """코사인 유사도 상위 top_k 청크 반환 (score 내림차순)."""
    emb = _vec_literal(query_embedding)
    params: list = [emb]
    where = ""
    if sources:
        where = "WHERE source = ANY(%s)"
        params.append(list(sources))
    params += [emb, top_k]

    sql = f"""
        SELECT source, page, chunk_index, content,
               1 - (embedding <=> %s::vector) AS score
        FROM documents
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_sources(conn) -> list[dict]:
    """적재된 PDF별 청크 수 통계."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source, COUNT(*) AS chunks, MAX(created_at) AS ingested_at
            FROM documents
            GROUP BY source
            ORDER BY source
            """
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def count_chunks(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM documents")
        return cur.fetchone()[0]
