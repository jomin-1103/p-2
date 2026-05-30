-- pgvector 확장 및 스키마 초기화
-- docker-entrypoint-initdb.d 로 마운트되어 DB 최초 생성 시 자동 실행되며,
-- `python -m src.init_db` 로도 (멱등하게) 다시 실행할 수 있습니다.

CREATE EXTENSION IF NOT EXISTS vector;

-- 기출 PDF 청크 + 임베딩 저장 테이블
-- 임베딩 차원은 bge-m3 기준 1024. 모델을 바꾸면 vector(N) 을 함께 수정하세요.
CREATE TABLE IF NOT EXISTS documents (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT        NOT NULL,            -- 원본 PDF 파일명
    page        INTEGER,                         -- PDF 페이지 번호 (1-base)
    chunk_index INTEGER     NOT NULL,            -- 페이지 내 청크 순번
    content     TEXT        NOT NULL,            -- 청크 본문
    embedding   vector(1024),                    -- 임베딩 벡터
    year        INTEGER,                         -- 시행 연도 (예: 2021)
    subject     INTEGER,                         -- 과목 번호 (1~5)
    metadata    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 기존 테이블이 있을 경우를 대비한 멱등 컬럼 추가
ALTER TABLE documents ADD COLUMN IF NOT EXISTS year    INTEGER;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS subject INTEGER;

-- 코사인 거리 기반 ANN 검색용 HNSW 인덱스
CREATE INDEX IF NOT EXISTS documents_embedding_idx
    ON documents USING hnsw (embedding vector_cosine_ops);

-- 파일 단위 조회/삭제 가속
CREATE INDEX IF NOT EXISTS documents_source_idx
    ON documents (source);

-- 연도/과목 필터(예: "21년도 1과목") 가속
CREATE INDEX IF NOT EXISTS documents_year_subject_idx
    ON documents (year, subject);
