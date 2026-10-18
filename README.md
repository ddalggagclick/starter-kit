<!-- 책임: [통합] 상속길잡이 Contract-first 모노레포의 최상위 길잡이.
구현할 기능: 최초 설치 2개 및 4개 영역 실행 명령을 하나의 루트 경로에서 안내한다.
완료 기준: RUN_FIRST.md와 명령/상태 일치, 파일 소유 경계 문서 연결. -->
# 상속길잡이 × AI 스타터킷

## 첫 설치 — 루트(`starter-kit/`)에서 2개

```bash
uv sync
npm --prefix frontend install
```

## 각 터미널에서 실행 — 루트에서 4개

```bash
uv run uvicorn inheritance.main:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
uv run starter-llm status
uv run starter-rag status
```

Frontend URL은 `http://localhost:5173/`, Backend 헬스는 `http://127.0.0.1:8000/health`입니다. CLI `status`는 실제 생성/검색을 수행하지 않고 계약 준비 상태를 반환합니다.

**전제 조건:** Python 3.13, uv, Node.js 24, npm, 인터넷 연결. Model checkpoint, Ollama 프로그램 및 Qwen 파일, Supabase 서비스는 설치 명령에 포함되지 않습니다.

- **실행 세부사항/예상 출력/빌드:** [`RUN_FIRST.md`](RUN_FIRST.md)
- **설치 및 실행:** [`RUN_FIRST.md`](RUN_FIRST.md); **개인 Ollama 설정:** [`.env.example`](.env.example)
- **RAG 의존성 설명:** [`rag/pyproject.toml`](rag/pyproject.toml) 주석
- **네이밍 및 책임:** [`docs/NAMING_CONVENTIONS.md`](docs/NAMING_CONVENTIONS.md), [`docs/PROJECT_STRUCTURE_GUIDE.md`](docs/PROJECT_STRUCTURE_GUIDE.md)
- **코드·계약 소유:** [`AGENTS.md`](AGENTS.md), [`CLAUDE.md`](CLAUDE.md), [`docs/CONTRACTS_START_HERE.md`](docs/CONTRACTS_START_HERE.md)
- **CI 권고:** [`AGENTS.md`](AGENTS.md)의 CI 권고 절
