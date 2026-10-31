<!-- 책임: [통합] 상속길잡이 스타터킷의 최상위 길잡이.
구현할 기능: bootstrap 프로필 선택, 설치, 실행 진입점을 루트 기준으로 안내한다.
완료 기준: RUN_FIRST.md와 프로필·명령·상태가 일치하고 파일 소유 경계 문서를 연결한다. -->
# 상속길잡이 × AI 스타터킷

## 최초 설정 — 루트(`starter-kit/`)에서 1개 명령

```bash
bash scripts/bootstrap.sh
```

메뉴에서 실행 범위를 고릅니다.

| 선택 | 설치 범위 |
|---|---|
| 상속길잡이 전체 | `uv sync --locked --group bootstrap`, `npm ci --prefix frontend` — Backend, Frontend, LLM, RAG |
| LLM CLI만 | `uv sync --package starter-llm --locked --group bootstrap` — Ollama failover 선택 시 `--extra ollama` 추가 |
| RAG CLI만 | `uv sync --package starter-rag --extra ingestion --locked --group bootstrap` |

세 프로필은 공통 `uv.lock`을 사용합니다. 프로필을 바꾸면 같은 `.venv`를 선택 범위로 다시 동기화하며 다른 프로필 패키지는 제거됩니다. Frontend는 전체 프로필에서만 설치합니다.

Bootstrap은 macOS/Linux/WSL의 실제 터미널에서 실행합니다. 처음 실행하기 전에 [Python 3.13](https://www.python.org/downloads/)과 [uv](https://docs.astral.sh/uv/getting-started/installation/)를 설치하고 PATH에서 실행할 수 있어야 합니다. 전체 프로필은 [Node.js 24.22.1 이상과 npm](https://nodejs.org/en/download/)도 필요합니다. 누락된 PostgreSQL·pgvector·Ollama는 자동 설치하지 않고 [PostgreSQL 설치 안내](https://www.postgresql.org/download/), [pgvector 설치 안내](https://github.com/pgvector/pgvector#installation), [Ollama 다운로드](https://ollama.com/download)를 표시합니다.

Bootstrap이 저장하는 API 키, DB URL, SMTP 자격정보, 토크나이저 경로는 `~/.config/starter-kit/config.json`에 Argon2id와 AES-256-GCM으로 암호화합니다. 새 암호 문구를 숨김 입력으로 두 번 확인하며, 설정을 읽는 각 독립 명령은 한 번 입력을 요청합니다. POSIX 디렉터리/파일 권한은 각각 `0700`/`0600`입니다. 암호 문구를 잊으면 저장 설정을 복구할 수 없어 bootstrap에서 자격정보를 다시 입력해야 합니다. 실행 중 서버는 요청마다 암호 문구를 묻지 않습니다.

기존 평문 `config.json`은 bootstrap 설정 흐름에서 암호화 파일로 전환합니다. 일반 실행은 평문 설정 파일을 거부하고 bootstrap 재설정을 안내합니다. 암호화는 저장 파일의 평문 노출을 줄이지만, 같은 사용자 권한으로 실행되는 프로세스에서 비밀값을 숨기지는 않습니다. RAG 패키지가 별도로 사용하는 `~/.config/starter-rag/config.json`은 이번 암호화 대상이 아닙니다.

전체 프로필에서 Backend는 Supabase PostgreSQL Session Pooler 설정을 사용하므로 로컬 PostgreSQL 설치는 필요하지 않습니다. RAG CLI의 로컬 색인·검색에는 PostgreSQL, `starter_rag_integration` DB, pgvector가 필요합니다. LLM CLI에는 PostgreSQL이 필요하지 않습니다. 선택한 LLM 공급자 키와 Ollama 실행 파일/서비스/모델은 사용자가 준비합니다.

`doctor`는 설치 완료와 런타임 준비 상태를 분리해 출력합니다. DB/API/모델 연결은 시도하지 않습니다. 런타임이 `MISSING`이어도 잠금 Python/npm 패키지 설치는 완료될 수 있습니다. 설정값이나 개인 경로는 출력하지 않습니다.

## 상속길잡이 서버 실행 — 각 명령을 별도 터미널에서, 루트에서 실행

```bash
.venv/bin/python scripts/local_env.py run uv run uvicorn app_entry:app --app-dir backend --port 8000
npm --prefix frontend run dev
```

Backend와 Frontend 개발 서버는 종료할 때까지 실행 상태로 둡니다. LLM·RAG 상태는 아래 일회성 명령으로 확인합니다.

LLM 단독 프로필은 `.venv/bin/python scripts/local_env.py run uv run --project llm --locked starter-llm status`, RAG 단독 프로필은 `.venv/bin/python scripts/local_env.py run uv run --project rag --extra ingestion --locked starter-rag status`를 사용합니다. Ollama failover를 선택했다면 LLM 명령에 `--extra ollama`를 `--locked` 앞에 추가합니다. 자세한 사용 예시는 [`RUN_FIRST.md`](RUN_FIRST.md)를 따릅니다.

Frontend URL은 `http://localhost:5173/`, Backend 헬스는 `http://127.0.0.1:8000/health`입니다. `app_entry:app`은 LLM·RAG·법령 Port를 조립하는 Backend 진입점입니다. `inheritance.main:app`은 조립된 채팅 서비스를 전달하지 않아 A08이 503을 반환합니다.

Frontend 화면을 실제 Backend에 연결하려면 `frontend/.env.development`에 다음 값을 설정합니다. `VITE_USE_MOCK_API`는 값이 정확히 `false`일 때만 Mock 대신 Backend 경로를 선택합니다. 값을 바꾼 뒤에는 Vite 개발 서버를 다시 시작합니다.

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK_API=false
```

현재 코드의 기능 구현과 통합 검증은 완료됐습니다. `starter-llm status`와 `starter-rag status`는 구현·설정 메타데이터를 출력하며 모델 생성, 검색, DB 연결을 실행하지 않습니다. RAG 상태의 `runtimeReadiness: not-checked`는 이 명령이 런타임 점검을 수행하지 않는다는 뜻입니다.

**전제 조건:** 모든 프로필에 Python 3.13, uv, 인터넷 연결이 필요합니다. 전체 프로필에는 Node.js 24.22.1 이상과 npm도 필요합니다. Ollama 프로그램·모델, 모델 가중치, PostgreSQL, Supabase 서비스는 설치하지 않습니다.

- **실행 세부사항/예상 출력/빌드:** [`RUN_FIRST.md`](RUN_FIRST.md)
- **설치 및 실행:** [`RUN_FIRST.md`](RUN_FIRST.md); **LLM 키 설정(Gemini·Groq):** [`.env.example`](.env.example)
- **RAG CLI 설치·운영:** [`rag/README.md`](rag/README.md); **RAG 의존성 설명:** [`rag/pyproject.toml`](rag/pyproject.toml) 주석
- **네이밍 및 책임:** [`docs/NAMING_CONVENTIONS.md`](docs/NAMING_CONVENTIONS.md), [`docs/PROJECT_STRUCTURE_GUIDE.md`](docs/PROJECT_STRUCTURE_GUIDE.md)
- **코드·계약 소유:** [`AGENTS.md`](AGENTS.md), [`CLAUDE.md`](CLAUDE.md), [`docs/CONTRACTS_START_HERE.md`](docs/CONTRACTS_START_HERE.md)
- **CI 권고:** [`AGENTS.md`](AGENTS.md)의 CI 권고 절
