<!--
담당: [A] | 책임: Mock 응답·클릭 Mock·Mock/Backend 전환을 안내한다.
완료 기준: Mock 시나리오와 Backend 연동 결과를 구분해 설명한다.
-->
# Frontend Mock과 데이터 연결

## 데이터 모드

`VITE_USE_MOCK_API`가 없거나 값이 정확히 `false`가 아니면 서비스 API는 Mock을 사용합니다. 실제 Backend를 호출하려면 `frontend/.env.development`에 다음 값을 설정합니다.

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK_API=false
```

`VITE_API_BASE_URL`은 `http://` 또는 `https://`로 시작하는 API origin이어야 합니다. 환경변수를 바꾼 뒤 Vite 개발 서버를 다시 시작합니다.

## Mock 파일

| 파일 | 역할 |
|---|---|
| `mock-api.ts` | A05·A07·A08·인증·A17의 가짜 API 응답, 지연·취소·오류 시나리오 |
| `wire-types.ts` | OpenAPI 0.2.1-draft (2026-10-22)의 Mock wire 타입 |
| `ai-stream.ts`, `mock-ai-scenario.ts` | 채팅 SSE 응답과 S3·S6·S7·S9 화면 시나리오 |
| `conversations.ts` | 저장 동의 전용 UI에 쓰는 대화 Mock 데이터 |
| `html-mock/` | 해시 라우팅으로 화면 흐름을 재현하는 클릭 Mock |

제품 화면의 공통 문구는 `shared/content/`에 있습니다. 주요 파일은 `procedures.ts`, `checklist.ts`, `general-info.ts`, `chat.ts`입니다. 이 콘텐츠와 API Mock 데이터는 서로 다른 역할을 합니다.

## Backend 전환 범위

`VITE_USE_MOCK_API=false`이면 구현된 API 모듈은 Backend 요청 경로를 사용합니다.

| 영역 | 실제 요청 |
|---|---|
| Handoff | A05 |
| 절차 | A07 목록·상세 |
| 채팅 | A08 POST SSE |
| 인증 | A11~A16 |
| 서버 체크리스트 | A17 GET·PUT·DELETE |

Backend는 인증 서비스 설정이 유효할 때 인증과 A17 라우터를 등록합니다. W-08 제보는 `VITE_USE_MOCK_API=false`에서도 Mock 모달입니다. `/mock.html`도 데이터 전환 변수와 관계없이 Mock API를 사용합니다.

## 클릭 Mock

`npm --prefix frontend run dev` 실행 후 `http://localhost:5173/mock.html`을 엽니다. `mock.html`은 개발용 진입점이며 `npm --prefix frontend run build` 결과에 포함되지 않습니다.

## 코드에 고정된 미확정 계약값

다음 항목은 화면 Mock 동작은 구현·검증됐지만 API·제품 값으로 확정되지 않았습니다. 각 항목의 현재 코드는 표시한 Mock 규칙을 사용합니다.

- `relatedProcedureIds` (D4): 공통 절차 콘텐츠에서 빈 배열을 사용합니다.
- 위험 질문과 절차의 연결표 (Q126 C): `shared/content/checklist.ts`의 Mock 배정을 사용합니다.
- W-04 상세 접기 상태 (M-10): 현재 화면은 신청 방법·필요 서류를 펼쳐 표시하고 예외·참고·문의처를 접어 표시합니다. 재방문 때 펼침 상태를 유지할지는 정해지지 않았습니다.
- A17 `itemStates` 내부 스키마: Frontend는 `server-checklist-api.ts`에서 현재 체크리스트 모양으로 변환합니다. OpenAPI는 내부 항목 구조를 확정하지 않았습니다.
- 대화 제목·목록 상한 (P02): 현재 코드는 첫 질문 앞 30 Unicode 코드 포인트로 제목을 만들고, 30개를 넘으면 말줄임표를 붙입니다. 제품 제목 규격과 목록 상한은 정해지지 않았으며, 현재 목록은 저장된 대화 전체를 표시합니다.
- S7 판단 유보 화면의 공식 확인 URL (S01): 현재 Mock은 확정 URL을 제공하지 않습니다.

Mock 화면과 Backend API 전환 흐름의 구현·검증을 완료했습니다. Mock 응답은 실제 API 응답으로 사용되지 않습니다.
