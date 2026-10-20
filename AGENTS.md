<!-- 책임: [통합] 모든 팀원·코딩 에이전트의 최상위 개발 규칙.
구현할 기능: 구조/소유권/보안/계약 우선순위 및 타 영역 수정 방지.
완료 기준: AGENTS.md와 CLAUDE.md 내용 동일, 각 폴더 소유권 및 승인 전 금지 규칙 명시. -->

# 상속길잡이 × AI 서비스 스타터킷 — 코딩 에이전트 규칙

> **반드시 먼저 읽기.** 이 저장소는 계약 우선(contract-first) 스캐폴드입니다. **전체 아키텍처는 아직 미승인**이며 현재 코드는 운영 완료물이 아닙니다.
> 사용자가 명확히 승인하지 않은 설계 변경, ERD/테이블 생성, 기능 추가 또는 범위 확대를 하지 마세요.

## 1. 시작 전 필수 행동

1. 루트의 `AGENTS.md`/`CLAUDE.md`와 **작업 디렉터리의** `AGENTS.md` 또는 `CLAUDE.md`를 확인한다.
2. **`docs/NAMING_CONVENTIONS.md`와 `docs/PROJECT_STRUCTURE_GUIDE.md`를 읽고** 파일명·함수명·배치 위치를 따르며, `docs/CONTRACTS_START_HERE.md`, `docs/ARCHITECTURE.md`, `docs/contracts/INTERFACE_FINAL_v1.md`, `docs/PROJECT_STRUCTURE_GUIDE.md`와 해당 파일의 상단 **책임/구현할 기능/완료 기준**을 읽는다. 문서 파일명이 달라졌다면 실제 저장소에서 검색하고 확인한다.
3. 이번 작업의 담당자 및 변경 허가 범위를 먼저 확인한다. **자기 영역 외 파일은 열람·참조만 가능하고 수정/이동/삭제/포맷/자동 생성 결과 덮어쓰기는 금지**한다.
4. 타 영역 변경이 필수라면 패치 제안·계약 변경 요청을 만들고 **그 파일 소유자 + 통합 관리자의 명시적 승인 이후 별도 PR**에서 수정한다. 작업을 위해서라는 이유로 임의 수정하지 않는다.
5. 모든 작업은 변경 파일 목록, 근거 계약 ID, 테스트 결과와 미검증 항목을 제시한다. 성공하지 않은 설치·실연동·E2E 테스트는 성공했다고 표현하지 않는다.

## 2. 현재 아키텍처와 의존 방향 (변경 금지)

- `frontend/`: **[A]** React 19 + TypeScript + Vite 8 + Tailwind v4 + shadcn/ui 호환 패턴; REST는 **공통 Axios** 단일 인스턴스, **POST SSE 응답만 fetch + ReadableStream**. Zustand는 임시 UI 상태, Dexie 4는 체크리스트/채팅 동의를 분리해 허용된 데이터만 IndexedDB 보관.
- `backend/src/inheritance/`: **상속 전용 FastAPI**. `[B]` `checklist/`, `chat/`, `law/`; `[C]` `kakao/` 및 `kakao/handoff/`; `[통합]` `auth/`, `core/`, `contracts/`, `main.py`, Alembic/DB 세션. HTTP 메서드·경로·JSON·SSE의 상세 전송 계약은 **API 담당자**가 소유한다.
- `llm/starter_llm/`: **[C]** 독립 Python 패키지. LangChain Core + `ChatGoogleGenerativeAI` / `ChatOllama`는 `ModelPort.generate/stream` 뒤에 감춘다. Backend는 SDK/내부 LangChain 객체를 import하지 않는다.
- `rag/starter_rag/`: **[D]** 독립 Python 패키지. Docling/EmbeddingGemma 2(768d)/PostgreSQL pgvector `PGVectorStore` 구현. Backend는 `SearchPort.search`와 공개 DTO만 안다. 검수 후 게시된 안내 자료만 검색 가능; **법령 원문을 RAG에 벡터 저장 금지**.
- 외부 연결: Frontend → Backend HTTP; Backend → LLM/RAG 공개 Port. **LLM/RAG → Backend 역참조 금지**, `llm ↔ rag` 서로 import 금지, 순환 의존 금지.
- 법령: `backend/law/`에서 `korean-law-mcp`로 조문·연혁을 가져오고, **관련 부칙 전문은 법제처 공식 OPEN API**로 조회. 해당 개정 법률의 자동 후보 선정은 필요할 때 검증 후 구현하는 조건부 업무.
- 호스팅: Render Static Site + Render Web Service. **DB는 Supabase PostgreSQL Session Pooler(5432)**; PostgreSQL 업무 원장은 Backend가, pgvector 사용은 RAG가 책임진다. ERD는 별도 결정 전 미승인. Render CD 템플릿은 승인 전 실행 금지.

## 3. 팀원별 소유 경계

| 소유자                      | 수정 허용 경로                                                                                                                                                                  | 금지 예시                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| [A] Frontend                | `frontend/**`                                                                                                                                                                   | `backend/**`, `llm/**`, `rag/**`, 루트 설정/워크플로                               |
| [B] Backend 도메인          | `backend/src/inheritance/{checklist,chat,law}/**`                                                                                                                               | `backend/auth`, `backend/core`, `backend/kakao`, `llm/**`, `rag/**`, `frontend/**` |
| [C] 카카오·LLM              | `backend/src/inheritance/kakao/**`, `llm/**`                                                                                                                                    | `backend/checklist`, `backend/chat`, `rag/**`, `frontend/**`                       |
| [D] RAG                     | `rag/**`                                                                                                                                                                        | `backend/**`, `llm/**`, `frontend/**`                                              |
| [통합] 조립/보안/환경/DB/CI | 루트 `pyproject.toml`, `.github/**`, `backend/src/inheritance/{auth,core,contracts}/**`, `backend/main.py`, `backend/migrations/**`, `backend/pyproject.toml`, 승인된 공통 문서 | 담당 기능의 내부 구현을 대리 수정 금지                                             |

- 경계가 중첩·불명확하면 **소유자에게 먼저 확인**한다. 통합 관리자라고 해서 다른 사람 업무 코드를 임의 수정하지 않는다.
- 소유자의 `pyproject.toml`/`package.json`은 해당 담당자가 제안할 수 있지만, **루트 lockfile 및 공용 의존성 변경은 통합 승인**을 받는다.
- API 담당자의 공개 HTTP 스키마 승인 없이 경로·상태 코드·SSE 와이어 형식을 확정하지 않는다.

## 4. 변경 불가 서비스 안전 규칙

- 초기 질문 3개, 선택 위험 질문 3개; 공통 절차 안내는 p01~p08 전체를 표현한다. `안내 확인`은 **읽음**이지 법률 절차 완료가 아니다.
- 내부 `GuidanceResult`의 `guidance`와 `risk_information`은 상세 구조 확정 전까지 임시 `object` 타입이다. 최종 HTTP API 타입, 출처 구조, 표시 순서는 이 계약에서 정하지 않는다.
- AI 입력 200 Unicode 코드 포인트, 지난 발화 3개, 추가 확인 질문 0회. LLM 기본 timeout 30초/허용 최대 300초, RAG TopK 기본 3/최대 10.
- 분류 1회 + 최종 답변 생성 1회 가능. Gemini 기본 모델; 개인 개발 PC에서 **유일한 `.env.example` 하단 주석을 참조해** 명시적 `LLM_PROVIDER=ollama`, `LLM_MODEL=qwen3:4b-instruct` 사용 가능. `.env.ollama.example` 파일은 사용하지 않는다. **429 발생 시 자동 공급자 전환/재시도 금지**; 다른 비AI 개발 진행. API 키 공유·커밋 금지.
- 출처 0건/판단 불가 → S7, 기술 오류 → S6, 제한 → S9. 인증 서버에 채팅 본문 영구 저장 금지. 각 출처의 제목·공식 URL·인용 위치 및 여러 법령/부칙을 반환할 수 있어야 한다.
- LLM은 동일 답변을 두 번 생성하지 않는다. 진행 상황은 SSE로 전송, **검증된 최종 답변만 브라우저에 전달하고 자동 타이핑 효과로 표시**. 강제 '다음 글자' 버튼, 전체 즉시 보기 버튼은 만들지 않는다.
- 인증은 FastAPI 자체 JWT Access(15분) + Argon2id + HttpOnly 회전 Refresh(7일), CSRF·CORS. Supabase Auth·브라우저 토큰 영속 저장 금지. 타사 쿠키 차단은 실브라우저 검증 후 CHIPS 여부 결정; 임의 채택 금지.
- `kakao` Handoff 10분·원자적 1회 사용, URL로 카카오 ID/비밀 유출 금지. 로그에 JWT/Refresh/원문 채팅/개인정보/키 남기지 않는다.
- RAG 문서 파싱/인덱싱은 관리자 CLI에서 명시적으로 실행. 서버 시작 시 자동 파싱·인덱싱 금지. ERD·마이그레이션은 승인 전 생성·실행 금지.

## 5. 네이밍·소스 배치·RAG 의존성 원칙

- **TypeScript/React 파일:** 소스 파일은 `kebab-case`(표준 도구 파일명 예외), 컴포넌트/타입은 PascalCase, 함수/변수는 camelCase, 상수는 UPPER_SNAKE_CASE.
- **Python 파일/함수/변수:** PEP 8 `snake_case`, 클래스/Protocol/예외는 PascalCase. Python 모듈 파일에 하이픈 금지.
- **DB 스키마/테이블/컬럼:** `snake_case` (ERD 승인 전 생성 금지); **API JSON 필드**는 I01 `camelCase` 원칙, 최종 wire는 API 담당자 승인.
- 신규 공통 코드를 도메인 폴더 밖에 두기 전 사용 범위를 확인한다. Frontend는 `features/<domain>` 우선, 둘 이상 공유할 때 `shared/`; Backend는 승인된 `contracts/`와 `core/`만 공통 경계로 사용한다.
- 상세 표/예외/테스트 규칙: `docs/NAMING_CONVENTIONS.md`. 각 폴더·파일 책임: `docs/PROJECT_STRUCTURE_GUIDE.md`.
- RAG 직접 의존성의 역할은 `rag/pyproject.toml` 항목별 주석을 확인한다. 실제 모델 설치는 별도다.

## 6. 설치·테스트 및 역할별 명령

```bash
# 루트: Python 3.13 + uv; 승인된 Python 의존성 처음 한 번에 설치
uv sync
uv run uvicorn inheritance.main:app --reload --port 8000
uv run python scripts/verify_contracts.py
uv run python -m unittest discover -s tests -v
uv run pytest tests
uv run ruff check backend llm rag tests

# frontend: Node.js 24 + npm; 승인된 npm 의존성 처음 한 번에 설치
cd frontend
npm install
npm run dev
npm run build
npm run typecheck
npm run lint
npm run test

# 루트 CLI (외부 모델/RAG 기능은 아직 미구현)
uv run starter-llm status
uv run starter-rag status
```

- `uv sync`/`npm install`은 최초 **일괄 설치**용이다. 이후 선언/lockfile/플랫폼이 달라지면 다시 동기화한다. `uv.lock`/`frontend/package-lock.json`은 **실제 온라인 lock 해결 후 통합 관리자 PR로 커밋**한다. 모델 가중치·Ollama 프로그램·DB 확장·법령 MCP Node 서버는 패키지 매니페스트 설치 대상이 아니다.
- 패키지 추가·범위 수정은 소유자 + 통합 승인과 lockfile 업데이트가 선행되어야 하며, 승인 없이 편의 라이브러리를 도입하지 않는다.
- `uv sync`/`npm install`의 실제 성공 여부를 확인하지 않고 '재현 설치 완료'라고 주장하지 않는다.

## 7. PR 규칙과 CI 권고

- PR은 한 소유 영역/한 계약 변경을 원칙으로. 변경 파일·공개 타입 영향·테스트 추가·롤백 방법을 적는다.
- **CI 권고:** 현재 검사는 `scripts/verify_contracts.py`를 사용한다. 추가 검사는 아래 권고 점검 목록을 참조한다.
- 권고 점검: uv lock 재현, Ruff lint+format, pytest/비동기 테스트, npm ci, Biome lint+format(Prettier는 별도 도입하지 않음), TypeScript typecheck, Vitest, Vite build, Port 제공자-소비자 테스트, OpenAPI 생성 diff, Alembic/pgvector 검증, 시크릿 유출 검사, 배포 승인 보호.
