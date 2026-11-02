<!--
담당: [A] | 책임: AI 채팅 화면, POST SSE, 저장 동의와 대화 기록.
구현할 기능: 질문 전송·취소·결과 표시·동의한 기록의 저장과 재열기.
완료 기준: Mock/Backend 응답과 저장 동의 상태를 분리해 표현한다.
-->
# AI 채팅

## 질문 전송

`chat-page.tsx`와 첫 화면의 `home-chat-window.tsx`가 공통 `use-chat-stream.ts`를 사용합니다. 기본 Mock 모드에서는 Mock SSE 응답을 사용합니다. `VITE_USE_MOCK_API=false`에서는 `ask-transport.ts`가 `POST /api/ai/ask`를 `fetch`와 `ReadableStream`으로 호출합니다. 요청은 질문, 요청 ID, 이전 사용자 질문 최대 3개를 포함합니다.

`use-chat-stream.ts`와 `sse-parser.ts`가 진행 이벤트·최종 결과·오류를 처리하고, 화면을 벗어나거나 사용자가 취소하면 해당 요청의 `AbortController`를 중단합니다. 검증된 최종 답변은 자동 타이핑으로 표시합니다.

## 대화 기록

`chat-storage.ts`와 `chat-history.tsx`가 대화 저장 동의, 목록·열기·삭제를 관리합니다. 체크리스트 저장 동의와 채팅 저장 동의는 별개입니다. 동의한 대화만 Dexie에 저장합니다. S3 답변은 답변과 출처를 저장하고, S7 판단 유보는 질문만 저장하며, S6 기술 오류와 S9 제한은 저장하지 않습니다.

채팅 UI·SSE 전송·저장 동의 구현과 통합 검증을 완료했습니다. Backend 연결은 `backend/app_entry.py`가 채팅 서비스를 조립해 제공합니다.
