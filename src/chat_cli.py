"""터미널에서 빠르게 테스트하기 위한 CLI 챗봇.

사용:
    python -m src.chat_cli            # qa 모드
    python -m src.chat_cli --mode quiz
"""
from __future__ import annotations

import argparse

from . import rag


def main() -> None:
    parser = argparse.ArgumentParser(description="기출 RAG 챗봇 (CLI)")
    parser.add_argument("--mode", choices=list(rag.MODE_LABELS), default="qa")
    args = parser.parse_args()

    print(f"모드: {rag.MODE_LABELS[args.mode]}  (종료: Ctrl+C 또는 'exit')")
    history: list[dict] = []
    while True:
        try:
            query = input("\n질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break
        if not query or query.lower() in {"exit", "quit"}:
            break

        gen, sources = rag.generate(query, mode=args.mode, history=history)
        print("\n답변:")
        full = []
        for token in gen:
            print(token, end="", flush=True)
            full.append(token)
        print()

        if sources:
            print("\n참고 자료:")
            for i, s in enumerate(sources, start=1):
                loc = f"{s['source']} p.{s['page']}" if s.get("page") else s["source"]
                print(f"  [{i}] {loc} (유사도 {s['score']:.3f})")

        answer_text = "".join(full)
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": answer_text})


if __name__ == "__main__":
    main()
