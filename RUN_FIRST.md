<!-- 책임: [통합] bootstrap 프로필 선택, 설치, 설정과 실행을 한 흐름으로 안내한다.
구현할 기능: 상속길잡이 전체, LLM CLI, RAG CLI 프로필을 루트에서 준비하고 실행한다.
완료 기준: 선택별 설치 명령, 설정 보안, 실행 명령과 미설정 상태를 정확히 안내한다. -->
# 한 명령으로 개발 환경 설정

**macOS/Linux/WSL의 실제 터미널에서 저장소 루트(`starter-kit/`)로 실행하세요.** 먼저 Python **3.13**과 `uv`를 설치하고 PATH에서 실행할 수 있어야 합니다. Bootstrap은 누락된 시스템 프로그램을 자동 설치하지 않습니다. 누락을 발견하면 공식 설치 안내를 표시하고 중단합니다.

| 프로그램 | 필요한 프로필 | 공식 설치 안내 |
|---|---|---|
| Python 3.13 | 전체, LLM, RAG | [Python 다운로드](https://www.python.org/downloads/) |
| uv | 전체, LLM, RAG | [uv 설치](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js 24.22.1 이상 및 npm | 전체 | [Node.js 다운로드](https://nodejs.org/en/download/), [npm 설치 안내](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm/) |
| PostgreSQL 및 pgvector | RAG CLI의 로컬 색인·검색 | [PostgreSQL 설치](https://www.postgresql.org/download/), [pgvector 설치](https://github.com/pgvector/pgvector#installation) |
| Ollama | Ollama를 선택한 경우 | [Ollama 다운로드](https://ollama.com/download) |

PostgreSQL과 pgvector는 자동 설치하지 않습니다. 전체 앱은 설정된 Supabase Session Pooler를 사용하므로 로컬 PostgreSQL이 필요하지 않고, LLM CLI도 PostgreSQL을 요구하지 않습니다.

```bash
bash scripts/bootstrap.sh
```

## 1. 실행 프로필 선택

| 메뉴 | 설치 범위 | 설치 명령 |
|---|---|---|
| 상속길잡이 전체 | Backend, Frontend, LLM, RAG | `uv sync --locked --group bootstrap` 및 `npm ci --prefix frontend` |
| LLM CLI만 | LLM 패키지 | `uv sync --package starter-llm --locked --group bootstrap` |
| RAG CLI만 | RAG 파싱·청킹·색인·검색 CLI | `uv sync --package starter-rag --extra ingestion --locked --group bootstrap` |

LLM 프로필에서 Ollama failover를 선택하면 `uv sync --package starter-llm --extra ollama --locked --group bootstrap`를 사용합니다. 전체 프로필만 Node.js **24.22.1 이상**과 `npm`을 요구합니다. LLM/RAG 프로필은 Node.js를 요구하지 않습니다.

세 프로필은 공통 `uv.lock`과 루트 `.venv`를 사용합니다. 프로필을 바꾸면 `.venv`가 선택 범위로 다시 동기화되고, 다른 프로필 패키지는 제거됩니다. Frontend의 `node_modules`는 전체 프로필에서만 설치합니다.

## 2. 비밀 설정 입력

Bootstrap은 API 키, DB URL, SMTP 자격정보, Kakao Handoff 공유 비밀, 토크나이저 경로를 숨김 입력으로 받습니다. Enter를 누르면 해당 설정은 건너뜁니다. 앱용 JWT·CSRF·Handoff 해시 키는 기존 값이 없을 때만 로컬 난수로 만들고 화면에 출력하지 않습니다. 저장된 값은 입력 화면, 설치 로그, doctor 결과에 표시되지 않습니다.

개인 설정은 `~/.config/starter-kit/config.json`에 Argon2id 키 파생과 AES-256-GCM으로 암호화해 저장합니다. 새 암호 문구를 숨김 입력으로 두 번 확인합니다. 암호화된 설정을 읽는 각 독립 명령은 한 번 잠금 해제 입력을 받습니다. POSIX에서 디렉터리/파일 권한은 각각 `0700`/`0600`입니다. Bootstrap은 비밀값·암호 문구 입력을 숨길 수 없는 비대화형 터미널에서 중단합니다.

암호 문구를 잊으면 기존 설정을 해독할 수 없습니다. bootstrap을 다시 실행해 새 암호 문구를 만들고 API 키와 접속 정보를 다시 입력해야 합니다. 이전 평문 설정은 bootstrap 설정 과정에서만 암호화 파일로 전환되며, 일반 실행은 평문 파일을 거부합니다. 암호화는 저장 파일이 복사됐을 때 평문 노출을 줄이지만, 실행 중 같은 사용자 권한으로 동작하는 프로세스에는 설정값이 전달됩니다. RAG 패키지의 별도 `~/.config/starter-rag/config.json`은 이 암호화 기능에 포함되지 않습니다.

`local_env.py run`은 저장 설정을 자식 명령에 전달합니다. 셸에 같은 이름의 환경변수가 있으면 셸 값이 우선합니다.

전체 프로필의 `frontend/.env.development`는 읽기만 합니다. `VITE_API_BASE_URL=http://localhost:8000`, `VITE_USE_MOCK_API=false`인지 점검하며 파일을 덮어쓰지 않습니다.

## 3. 선택한 프로필 실행

### 상속길잡이 전체

Backend와 Frontend를 각각 별도 터미널에서 실행합니다.

```bash
.venv/bin/python scripts/local_env.py run uv run uvicorn app_entry:app --app-dir backend --port 8000
npm --prefix frontend run dev
```

Backend 헬스 주소는 `http://127.0.0.1:8000/health`, Frontend 주소는 `http://localhost:5173/`입니다. Frontend가 실제 Backend를 호출하려면 `VITE_USE_MOCK_API`가 정확히 `false`여야 합니다.

전체 앱의 채팅은 DB URL, LLM 키, `LAW_OC`, 승인된 `RAG_COLLECTION_ID` 설정이 필요합니다. 설정이 빠지면 서버는 시작할 수 있지만 채팅은 503으로 응답합니다. Kakao Handoff와 메일 기능은 각각 공유 비밀 또는 SMTP 설정이 있어야 동작합니다.

### LLM CLI만

상태를 확인하거나 실제 생성을 실행합니다.

```bash
.venv/bin/python scripts/local_env.py run uv run --project llm --locked starter-llm status
.venv/bin/python scripts/local_env.py run uv run --project llm --locked starter-llm generate --prompt "안녕하세요"
```

Gemini 또는 Groq 키가 있어야 생성할 수 있습니다. Ollama failover를 설치했다면 명령에 `--extra ollama`를 추가합니다.

Ollama failover를 선택한 경우의 실행 명령:

```bash
.venv/bin/python scripts/local_env.py run uv run --project llm --extra ollama --locked starter-llm generate --prompt "안녕하세요"
```

### RAG CLI만

상태를 확인하고 일반 RAG CLI 도움말을 실행합니다.

```bash
.venv/bin/python scripts/local_env.py run uv run --project rag --extra ingestion --locked starter-rag status
.venv/bin/python scripts/local_env.py run uv run --project rag --extra ingestion --locked starter-rag --help
```

RAG CLI의 로컬 검색·색인에는 PostgreSQL 서버, `starter_rag_integration` 데이터베이스, pgvector와 EmbeddingGemma 모델이 필요합니다. 문서 청킹에 Ollama를 선택하면 Ollama 실행 파일, 서비스와 선택 모델도 준비해야 합니다. Ollama 프로그램·모델, DB, 모델 가중치는 Bootstrap이 설치하지 않습니다. 명령별 준비와 실행은 [`rag/README.md`](rag/README.md)를 따릅니다.

## 4. 진단과 재설정

Bootstrap 마지막 doctor 출력은 Python/npm 패키지 설치 상태와 `RUNTIME PREREQUISITE: MISSING`을 분리합니다. 전체 프로필의 Frontend API 모드, 선택 공급자 자격정보, PostgreSQL·pgvector·Ollama 실행 파일을 점검합니다. DB 서비스, Ollama 서비스/모델, 외부 API에는 연결하지 않습니다. 설정값과 개인 경로는 출력하지 않습니다. 런타임 항목이 누락돼도 잠금 패키지 설치가 성공하면 bootstrap은 완료 코드 `0`을 반환합니다.

설정을 추가하거나 기존 값을 교체하려면 다음 명령으로 Bootstrap을 다시 실행하고 같은 프로필을 선택합니다.

```bash
bash scripts/bootstrap.sh
```

Bootstrap은 lockfile이 없으면 설치를 시작하지 않습니다. `uv sync`와 `npm ci`의 상세 출력은 화면에 표시하지 않습니다. 설치가 실패하면 명령 이름과 종료 코드가 표시되며, 상세 오류는 안내된 설치 명령을 직접 실행해 확인합니다.

## 검증 상태

프로그램 기능 구현과 통합 검증은 완료됐습니다. 개별 빌드·테스트 명령을 다시 실행할 필요는 없습니다. 전체 아키텍처와 ERD는 최종 승인되지 않았습니다.
