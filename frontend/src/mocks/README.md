<!--
담당: [A] | 책임: Mock 데이터·Mock API·클릭 Mock의 범위와 사용법.
완료 기준: Mock 결과를 실제 연동·검수 완료로 오인하지 않는다.
-->
# Mock (10/23 1차 발표 · 화면 개발용)

**실제 Backend · LLM · RAG · DB 연동이 아닙니다.** 문구 · 기한 · 링크는 검수 전 예시입니다.

## 근거

- `docs/contracts/openapi.yaml` 0.2.0-draft (2026-10-21): 경로 · 필드 · enum · 오류 코드
- 화면정의서 v1.4 (2026-10-16): 화면 ID · 문구 · 상태 · 예외(D-01~D-17)

## 파일

| 파일 | 내용 | API / 화면 |
|---|---|---|
| `wire-types.ts` | openapi 스키마를 옮긴 Mock 전용 타입 | 전체 |
| `procedures.ts` | 절차 8개 목록 · 상세 · 기한 꼬리표 | A07 · W-02 · W-03 · W-04 · K-04 |
| `checklist.ts` | 초기 3문항 · 위험 질문 3개 · 공통 경고 · 저장 상태 · 진입 시나리오 | W-01 · W-02 R/P/C · K-01~K-03 |
| `ai-stream.ts` | SSE `Response` 생성기 · 시나리오(S3/S6/S7/S9) · S1/S7 문구 | A08 · W-07 |
| `conversations.ts` | 이전 대화 · S8 · S11 문구 | W-07 S8 · S10 · S11 |
| `general-info.ts` | 상속 관계 · 상속세 · 오류 제보 Mock | W-05 · W-06 · W-08 |
| `mock-api.ts` | 지연 · 취소 · HTTP 오류를 흉내 내는 함수 | A05 · A07 · A08 · A11~A17 |

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
