"""DB 스키마 초기화 CLI.

사용:
    python -m src.init_db
"""
from __future__ import annotations

from . import db


def main() -> None:
    db.init_schema()
    with db.get_connection() as conn:
        total = db.count_chunks(conn)
    print(f"✅ 스키마 준비 완료. 현재 적재된 청크 수: {total}")


if __name__ == "__main__":
    main()
