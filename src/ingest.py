"""기출 PDF → 텍스트 추출 → 청킹 → 임베딩 → PostgreSQL 적재.

사용 예:
    # data/pdfs 폴더의 모든 PDF 적재
    python -m src.ingest

    # 특정 파일/폴더 지정, 이미 적재된 파일도 강제 재적재
    python -m src.ingest --path data/pdfs/2023_정보보안산업기사.pdf --force
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pypdf import PdfReader

from . import db, embeddings
from .config import settings

DEFAULT_DIR = Path("data/pdfs")

# "1과목", "제 1 과목" 등 과목 헤더 패턴
_SUBJECT_RE = re.compile(r"제?\s*([1-5])\s*과목")
# 4자리(2013) 또는 '21년' 형태의 2자리 연도
_YEAR4_RE = re.compile(r"(19|20)\d{2}")
_YEAR2_RE = re.compile(r"(\d{2})\s*년")


def detect_year(filename: str, first_text: str = "") -> int | None:
    """파일명 → 본문 순으로 시행 연도를 추정."""
    for text in (filename, first_text):
        m = _YEAR4_RE.search(text)
        if m:
            return int(m.group(0))
        m = _YEAR2_RE.search(text)
        if m:
            yy = int(m.group(1))
            return 2000 + yy if yy < 90 else 1900 + yy
    return None


def detect_subject(text: str) -> int | None:
    """페이지 텍스트에서 마지막으로 등장한 과목 번호를 반환."""
    matches = _SUBJECT_RE.findall(text)
    return int(matches[-1]) if matches else None


def extract_pages(path: Path) -> list[tuple[int, str]]:
    """(페이지번호, 텍스트) 목록 반환."""
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        pages.append((i, page.extract_text() or ""))
    return pages


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """공백 정규화 후 오버랩 슬라이딩 윈도우로 청킹."""
    text = " ".join(text.split())
    if not text:
        return []
    if size <= overlap:
        raise ValueError("CHUNK_SIZE 는 CHUNK_OVERLAP 보다 커야 합니다.")
    step = size - overlap
    return [text[i:i + size] for i in range(0, len(text), step) if text[i:i + size].strip()]


def ingest_pdf(conn, path: Path, *, force: bool = False) -> int:
    """단일 PDF 를 적재하고 삽입된 청크 수를 반환."""
    source = path.name
    if db.source_exists(conn, source):
        if not force:
            print(f"⏭️  이미 적재됨, 건너뜀: {source} (재적재하려면 --force)")
            return 0
        removed = db.delete_source(conn, source)
        print(f"♻️  기존 청크 {removed}개 삭제 후 재적재: {source}")

    pages = extract_pages(path)
    first_text = pages[0][1] if pages else ""
    year = detect_year(source, first_text)

    rows: list[dict] = []
    current_subject: int | None = None  # 과목 헤더는 이후 페이지로 전파
    for page_no, text in pages:
        found = detect_subject(text)
        if found is not None:
            current_subject = found
        chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
        for idx, chunk in enumerate(chunks):
            rows.append({
                "source": source,
                "page": page_no,
                "chunk_index": idx,
                "content": chunk,
                "year": year,
                "subject": current_subject,
            })

    print(f"   ↳ 감지된 연도: {year or '미상'}, "
          f"태깅된 과목 수: {len({r['subject'] for r in rows if r['subject']})}")

    if not rows:
        print(f"⚠️  추출된 텍스트가 없습니다(스캔 이미지 PDF일 수 있음): {source}")
        return 0

    print(f"🔎 {source}: {len(rows)}개 청크 임베딩 중...")
    vectors = embeddings.embed_texts([r["content"] for r in rows])
    for r, v in zip(rows, vectors):
        r["embedding"] = v

    inserted = db.insert_chunks(conn, rows)
    print(f"✅ {source}: {inserted}개 청크 적재 완료")
    return inserted


def collect_pdfs(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("*.pdf"))
    if path.is_file() and path.suffix.lower() == ".pdf":
        return [path]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="기출 PDF 를 PostgreSQL(pgvector)에 적재")
    parser.add_argument("--path", type=Path, default=DEFAULT_DIR,
                        help="PDF 파일 또는 폴더 경로 (기본: data/pdfs)")
    parser.add_argument("--force", action="store_true",
                        help="이미 적재된 파일도 재적재")
    args = parser.parse_args()

    pdfs = collect_pdfs(args.path)
    if not pdfs:
        print(f"❌ PDF 를 찾을 수 없습니다: {args.path}")
        print("   data/pdfs/ 폴더에 PDF 를 넣고 다시 실행하세요.")
        sys.exit(1)

    db.init_schema()
    total = 0
    with db.get_connection() as conn:
        for pdf in pdfs:
            total += ingest_pdf(conn, pdf, force=args.force)
    print(f"\n🎉 완료: 총 {total}개 청크 적재 ({len(pdfs)}개 파일 처리)")


if __name__ == "__main__":
    main()
