<!-- 책임: [통합] 네 언어/저장소의 이름과 주석 규칙을 통일한다.
구현할 기능: TypeScript, Python, DB, HTTP 필드, 파일 이름과 주석 작성 기준을 구분한다.
완료 기준: 표와 예시를 보고 이름과 주석을 일관되게 정한다. -->
# 네이밍·주석 규칙 — 코드 이름과 설명을 어떻게 정하는가

- **문서 버전:** v1
- **목적:** 이름과 주석으로 코드의 역할·경계를 이해하고, 서로 다른 언어의 규칙 충돌을 막는다.
- **적용:** 앞으로 작성할 코드. **기존 공개 Port·DTO 이름은 승인 없이 변경하지 않는다.**

## 1. 표기법

| 표기법 | 예시 | 사용처 |
|---|---|---|
| PascalCase | `UserProfile` | 타입·클래스·React 컴포넌트 |
| camelCase | `getUserName` | TypeScript 변수·함수·API JSON 필드 |
| kebab-case | `user-profile.tsx` | 직접 작성한 TS/TSX 파일 |
| snake_case | `get_user_name` | Python 함수·모듈·DB 테이블·컬럼 |
| UPPER_SNAKE_CASE | `MAX_COUNT` | 상수·환경변수 |

## 2. 대상별 규칙

| 대상 | 규칙 | 올바른 예 |
|---|---|---|
| React 컴포넌트 / TS 타입·인터페이스 | PascalCase | `ProcedureCard`, `AnswerReference` |
| Python 클래스·Protocol·Pydantic DTO | PascalCase | `ChecklistService`, `LawQuery` |
| TypeScript 함수·변수·훅 | camelCase | `getAnswer()`, `useChatStream()` |
| Python 함수·변수·메서드 | snake_case | `verify_source()`, `request_id` |
| 불변 상수 / ENV | UPPER_SNAKE_CASE | `TOP_K_MAX`, `DATABASE_URL` |
| **HTTP JSON 필드** | camelCase | `requestId`, `deathDateUnknown` |
| **DB 스키마·테이블·컬럼** | snake_case | `refresh_sessions`, `created_at` |
| Frontend 폴더 | kebab-case | `features/checklist` |
| Python 패키지·모듈 | snake_case | `starter_rag`, `prompt_builder.py` |

**HTTP DTO:** Python 내부는 `snake_case`를 유지할 수 있다. API 경계에서는 API 담당자가 승인한 `camelCase` JSON을 사용한다. TypeScript 타입은 OpenAPI로 생성한다.

## 3. 파일명

```text
좋음                              피함
user-profile.tsx                  UserProfile.tsx
use-chat-stream.ts                useChatStream.ts
prompt_builder.py                 prompt-builder.py  # Python import 불가
citation_validation.py            CitationValidation.py
```

**표준 도구 이름은 예외다.** `main.tsx`, `vite.config.ts`, `vite-env.d.ts`, `tsconfig.*.json`, `components.json`, `package.json`, `__init__.py`, `pyproject.toml`, `AGENTS.md`, `CLAUDE.md`, `README.md`는 바꾸지 않는다.

## 4. 파일과 테스트 배치

| 목적 | 기본 위치 / 파일명 |
|---|---|
| Frontend 단일 도메인 | `frontend/src/features/<domain>/` |
| Frontend 둘 이상 공유 | `frontend/src/shared/` 또는 `lib/` |
| Backend HTTP 진입 | `<domain>/router.py` |
| Backend 업무 흐름 | `<domain>/service.py` |
| Backend 영속 접근 | `<domain>/repository.py` |
| Backend DTO | `<domain>/schemas.py` 또는 승인된 `contracts/` |
| Python 테스트 | `tests/test_<feature>.py`, `test_<behavior>()` |
| TypeScript 테스트 | `*.test.ts` 또는 `*.test.tsx` (일관되게 유지) |

## 5. 주석 규칙

**목적:** 코드만으로 알기 어려운 의도·계약·제약을 설명한다. 주석은 코드를 읽어 그대로 옮기지 않는다.

### 5.1 언제 주석을 쓰는가

- 이름과 타입만으로 드러나지 않는 **이유, 보안 경계, 예외 처리, 외부 계약, 불변 조건**을 설명한다.
- 공개 Port, 복잡한 흐름, 인증·개인정보 처리처럼 잘못 이해하면 동작이나 안전성에 영향을 주는 함수는 필요한 동작과 보장을 설명한다.
- 짧고 명확한 함수에는 의무적으로 주석을 달지 않는다. 주석보다 이름이나 코드 구조를 개선하면 의도가 더 명확해지는지 먼저 확인한다.
- 파일 상단 주석은 파일의 책임과 범위를 설명한다. 함수 주석은 해당 함수의 책임과 계약만 설명한다.

### 5.2 함수 주석 작성법

함수 바로 위에 주석을 달면 호출자가 알아야 하는 기능과 계약을 구체적으로 쓴다.

- **기능:** 함수가 어떤 입력을 처리하고 어떤 결과를 만드는가?
- **조건:** 허용하는 입력, 유지하는 불변 조건, 거부하는 상황은 무엇인가?
- **결과:** 반환값의 의미, 부작용, 실패 시 동작은 무엇인가?
- 위 항목 중 코드와 이름만으로 분명하지 않은 내용만 쓴다. 매개변수 이름이나 반환 타입을 문장으로 반복하지 않는다.
- 여러 요구사항을 한 문장에 섞지 않는다. 함수와 주석 사이에 다른 선언을 두지 않는다.

나쁜 예:

```python
# 질문을 분류한다.
async def classify(question: str) -> RouteDecision: ...
```

좋은 예:

```python
# 질문의 검색 경로만 분류한다. 법령 힌트는 공식 조회 결과로 검증해야 한다.
async def classify(question: str) -> RouteDecision: ...
```

좋은 예는 분류 결과의 경계와 후속 검증 조건을 알려준다. 함수 이름과 타입을 반복하지 않는다.

### 5.3 내부 주석과 TODO

- 내부 주석은 바로 아래 코드의 **이유나 중요한 제약**을 설명한다. 코드 줄마다 동작을 번역하지 않는다.
- 예외 처리 주석은 왜 그 예외 범위를 잡는지, 실패를 어떻게 처리하는지 적는다.
- TODO는 담당자, 실제 PRD ID 또는 해결 조건, 남은 작업을 명시한다. PRD에 없는 ID를 만들지 않는다.
- “나중에 구현”, “확인 필요”처럼 담당자·조건·행동이 없는 TODO는 남기지 않는다. 완료되었거나 더 이상 유효하지 않은 TODO는 제거한다.
- 주석 처리한 실행 코드는 저장소 이력이 보관하므로 남기지 않는다. 저자·변경 이력·장식용 배너도 추가하지 않는다.

### 5.4 정확성 및 표기

- 주석은 한국어로 짧고 직접적으로 쓴다. 함수명, 타입명, 기술명, 실제 PRD ID는 원문 표기를 유지한다.
- 주석이 설명하는 코드 바로 옆에 둔다. 다른 함수나 시스템 전체에 관한 설명을 국소 코드 주석으로 쓰지 않는다.
- 현재 동작과 앞으로 구현할 작업을 구분한다. 스캐폴드나 선언만 있는 코드를 완료된 기능처럼 설명하지 않는다.
- 계획된 동작은 계획임을 표시하고 완료 기준을 쓴다. 실제 동작은 확인된 사실만 설명한다.
- 코드 변경 시 관련 주석도 함께 확인한다. 코드와 달라진 주석은 수정하거나 삭제한다.
- Python 설명 주석은 `#`, TypeScript 설명 주석은 `//` 또는 유효한 `/* ... */`를 사용한다. Python docstring은 런타임의 `__doc__`에 노출될 수 있으므로 API 문서가 목적일 때만 사용한다.

### 5.5 AI 자체 점검

주석을 추가하거나 수정한 뒤 다음을 확인한다.

1. 이 주석이 코드나 이름에 없는 정보를 제공하는가?
2. 함수 주석이 실제 동작, 반환 조건, 실패 동작을 정확히 설명하는가?
3. 계획을 현재 구현으로 표현하거나, 코드보다 넓은 범위를 설명하지 않는가?
4. 담당자·PRD ID·제약을 추측하거나 새로 만들지 않았는가?
5. 주석을 제거해도 이해가 같다면 삭제하는 편이 낫지 않은가?

모든 질문에 답한 뒤에도 필요한 주석만 남긴다.

**참고:** [좋은 주석과 나쁜 주석](https://velog.io/@hangem422/clean-code-comment)

## 6. 품질 검사

- **Python:** Ruff lint와 format. 이름 규칙은 PEP 8을 우선한다.
- **Frontend:** Biome lint와 format. TypeScript 타입 검사는 `tsc`로 따로 수행한다.
- **DB:** ERD 승인 전 테이블을 만들지 않는다.
- 타 팀원 파일은 이름을 맞추기 위해서라도 **무단 변경·포맷하지 않는다**.
