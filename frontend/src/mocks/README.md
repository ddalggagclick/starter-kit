<!--
담당: [A] | 책임: Mock 데이터·Mock API·클릭 Mock의 범위와 사용법.
완료 기준: Mock 결과를 실제 연동·검수 완료로 오인하지 않는다.
-->
# Mock (10/23 1차 발표 · 화면 개발용)

**실제 Backend · LLM · RAG · DB 연동이 아닙니다.** 가짜 서버 응답과 Mock 전용 문구만 둡니다.

## 근거

- `docs/contracts/openapi.yaml` 0.2.0-draft (2026-10-21): 경로 · 필드 · enum · 오류 코드
- 화면정의서 v1.4 (2026-10-16): 화면 ID · 문구 · 상태 · 예외(D-01~D-17)

## 파일

| 파일 | 내용 | API / 화면 |
|---|---|---|
| `wire-types.ts` | openapi 스키마를 옮긴 Mock 전용 타입(절차 화면 타입은 `shared/contracts/procedure.ts`에서 가져옴) | 전체 |
| `ai-stream.ts` | SSE `Response` 생성기 · 시나리오(S3/S6/S7/S9) | A08 · W-07 |
| `conversations.ts` | 이전 대화 · S8 · S11 문구 | W-07 S8 · S10 · S11 |
| `mock-api.ts` | 지연 · 취소 · HTTP 오류를 흉내 내는 함수 | A05 · A07 · A08 · A11~A17 |

### 실제 화면 문구는 `shared/content/`로 옮겼습니다 (2026-10-27)

실제 서비스 화면에 나가는 문구가 이 폴더에 있어 가짜 데이터로 오해되던 문제를 고쳤습니다. 문구는 바꾸지 않고 위치만 옮겼습니다. Mock과 화면이 같은 파일을 함께 씁니다.

| 파일 | 내용 | 화면 |
|---|---|---|
| `shared/content/procedures.ts` | 절차 8개 원고(작성자 공식 원문 대조) · 기한 꼬리표 · 공식 링크. 백엔드 시험이 이 파일과 원고를 비교 | A07 · W-02 · W-03 · W-04 · K-04 |
| `shared/content/checklist.ts` | 초기 3문항 · 위험 질문 3개 · 공통 경고 · 저장 상태 · 진입 시나리오 | W-01 · W-02 R/P/C · K-01~K-03 |
| `shared/content/general-info.ts` | 상속 관계 · 상속세(B1 검수 완료) · 오류 제보 문구 | W-05 · W-06 · W-08 |
| `shared/content/chat.ts` | 예시 질문 · 개인정보 경고 · 판단 유보 · 진행 단계 · 하루 한도 | W-07 |

## 확인용 값

- Handoff 유효 토큰: `mock-handoff-valid` (1회만 성공, 나머지는 같은 400 `HANDOFF_INVALID`)
- 로그인: `demo@example.com` / `mockpass1` (5번 실패 후 429)

## 클릭 Mock

`npm run dev` 후 `http://localhost:5173/mock.html`. 개발 서버 전용이며 `npm run build` 결과에 포함되지 않습니다.

## 아직 정해지지 않은 것 (Mock 값으로 대신함)

- p01~p08과 절차 이름 대응(D6), 관련 절차 필드(D4), 위험-절차 연결표(Q126 C)
- W-04 '길 때' 접는 기준(S01), 초기 접힘(M-10)
- 공식 URL(S01) — 기관 대표 주소만 사용
- `itemStates` 구조(A17), 대화 제목 길이 · 목록 상한(P02)
