<!--
담당: [A] | 책임: GitHub 이슈 #36의 저장소 내 사본. 작업 1개 = 이슈 1개 = 커밋 1개 = PR 1개 규칙에 따른다.
원본: https://github.com/ddalggagclick/starter-kit/issues/36
-->
# [feat] AI 질문 SSE 응답 Mock과 시나리오 7개 (A08) #36

- **GitHub 이슈:** https://github.com/ddalggagclick/starter-kit/issues/36
- **브랜치:** `36-feat-mock-ai-stream` (`34-feat-mock-checklist` 위에 쌓음)
- **PR:** base `34-feat-mock-checklist` · close #36 · #34 PR이 머지된 뒤 머지
- **순서:** Mock 이슈 14개 중 4번째
- **변경 파일:** `frontend/src/mocks/ai-stream.ts`, 이 문서

## 목표

W-07 AI 질문 화면(S1~S9) 확인용으로 A08 POST /api/ai/ask의 SSE 응답을 흉내 내는 Mock을 만든다.
실제 fetch가 받는 것과 같은 text/event-stream Response를 만들어, 이후 use-chat-stream 파서를 Mock으로 시험할 수 있게 한다. 실제 Gemini·RAG 호출이 아니며 답변·출처는 예시다.

## 작업

- [x] `frontend/src/mocks/ai-stream.ts` 작성
  - 시나리오 7개: S3 출처 3개/1개, S7 판단 유보(출처 0개, 200 withheld), S6 503·504, S9 429 RATE_LIMITED·PROVIDER_RATE_LIMIT
  - 스트림 시작 전 오류는 HTTP 상태+JSON, 시작 후 오류는 error 이벤트
  - 200 코드 포인트·이전 질문 3개 초과는 자르지 않고 422
  - AbortSignal로 취소
  - S1 개인정보 경고·예시 질문, S7 판단 유보 문구, 진행 단계 문구
- [x] 이슈 문서 `frontend/docs/issues/` 작성

## 완료 조건

- `npx tsc -b`, `npx biome check src/mocks` 통과
- 시나리오별 이벤트 순서와 HTTP 상태 (mock-api.test.ts에서 검사, Mock 이슈 8번째)
- 근거: openapi A08·SseEvents, 화면정의서 v1.4 08·14장·부록3·4 (Q49 A·Q62·D-13 A), PRD 3-1-5

## 검증 메모

- import: `@/shared/contracts/ui`(tracked), `./wire-types`(#28)
- 작업 폴더 전체 기준 tsc·biome 통과. 이 커밋 단독 빌드는 따로 확인하지 않았다.
- 출처 URL은 기관 대표 주소이며 제목에 (Mock)을 붙였다. S7 공식 확인 경로 URL은 S01 확정 전 Mock이다.
