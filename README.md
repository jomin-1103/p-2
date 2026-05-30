# 🔐 정보보안산업기사 기출 RAG 챗봇

정보보안산업기사 **기출 PDF**를 PostgreSQL(+pgvector)에 적재하고, **bge-m3** 임베딩으로
의미 검색(RAG)한 뒤 **Ollama의 qwen2.5** 모델로 답변을 생성하는 챗봇입니다.

```
PDF (data/pdfs)  ──추출/청킹──▶  bge-m3 임베딩  ──▶  PostgreSQL + pgvector
                                                          │
질문 ──임베딩──▶ 유사 청크 검색(top-k) ──컨텍스트──▶ qwen2.5(Ollama) ──▶ 답변 + 출처
```

## ✨ 기능

- **기출 PDF 적재 파이프라인**: 텍스트 추출 → 청킹 → 임베딩 → DB 저장 (파일 단위 멱등 재적재 지원)
- **RAG 질의응답**: 검색된 기출 내용을 근거로 답변하고 출처(파일·페이지·유사도)를 표시
- **Ollama 부가 기능 모드**:
  - 💬 `qa` — 기출 기반 질의응답
  - 📖 `explain` — 문제·개념 단계별 해설
  - 📝 `quiz` — 기출 스타일 모의문제 생성
  - 🗂️ `summary` — 단원/주제 핵심 요약
- **Streamlit 웹 UI** + 터미널 CLI

## 🧩 사전 준비

1. **Docker** (PostgreSQL + pgvector 구동용)
2. **Python 3.10+**
3. **[Ollama](https://ollama.com)** 설치 후 모델 다운로드:
   ```bash
   ollama pull bge-m3
   ollama pull qwen2.5
   ```

## 🚀 설치 & 실행

```bash
# 1) 의존성
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) 환경변수
cp .env.example .env        # 필요 시 값 수정

# 3) PostgreSQL(pgvector) 기동
docker compose up -d

# 4) 스키마 초기화 (docker 최초 기동 시 자동 실행되지만, 멱등하게 다시 실행 가능)
python -m src.init_db

# 5) 기출 PDF 적재 — data/pdfs/ 에 PDF 를 넣은 뒤
python -m src.ingest

# 6) 챗봇 실행 (웹 UI)
streamlit run streamlit_app.py
#   또는 터미널에서
python -m src.chat_cli --mode qa
```

브라우저에서 `http://localhost:8501` 접속 후 사이드바에서 모드를 선택해 사용합니다.

## 🗂️ 프로젝트 구조

```
.
├── docker-compose.yml      # pgvector 포함 PostgreSQL
├── db/init.sql             # 확장/테이블/HNSW 인덱스
├── data/pdfs/              # 여기에 기출 PDF 배치 (gitignore)
├── streamlit_app.py        # Streamlit 진입점
├── requirements.txt
├── .env.example
└── src/
    ├── config.py           # 환경설정
    ├── db.py               # PostgreSQL + pgvector 접근
    ├── embeddings.py       # Ollama bge-m3 임베딩
    ├── ingest.py           # PDF → 청킹 → 임베딩 → 적재
    ├── init_db.py          # 스키마 초기화 CLI
    ├── rag.py              # 검색 + qwen2.5 생성 (모드별)
    ├── app.py              # Streamlit UI
    └── chat_cli.py         # 터미널 챗봇
```

## ⚙️ 설정 (.env)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DB_*` | ragdb/raguser/ragpass | PostgreSQL 접속 정보 |
| `OLLAMA_HOST` | http://localhost:11434 | Ollama 서버 주소 |
| `EMBED_MODEL` | bge-m3 | 임베딩 모델 |
| `LLM_MODEL` | qwen2.5 | 답변 생성 모델 |
| `EMBED_DIM` | 1024 | 임베딩 차원 (모델 변경 시 `db/init.sql` 의 `vector(N)` 도 수정) |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 800 / 150 | 청킹 크기/겹침 |
| `TOP_K` | 5 | 검색 청크 수 |

## 📌 참고

- 기출 PDF 원본은 저작권 이슈가 있을 수 있으므로 저장소에 커밋되지 않습니다(`data/pdfs/*` gitignore).
- **스캔(이미지) PDF**는 텍스트 추출이 되지 않습니다. 이 경우 OCR(예: `ocrmypdf`)로 텍스트 레이어를 먼저 추가하세요.
- 임베딩 모델을 바꾸면 차원이 달라질 수 있으니 `EMBED_DIM` 과 `db/init.sql` 의 `vector(N)` 를 함께 맞추고 재적재하세요.
