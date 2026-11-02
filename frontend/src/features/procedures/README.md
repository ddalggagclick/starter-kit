<!--
담당: [A] | 책임: 공통 절차 목록과 상세 안내 화면.
구현할 기능: A07 목록·상세 조회, Mock 전환, 응답 정규화와 화면 표시.
완료 기준: 누락된 선택 필드를 만들지 않고 유효한 공식 링크만 표시한다.
-->
# 절차 목록과 상세 안내

`procedures-page.tsx`, `procedure-detail.tsx`, `procedure-steps.tsx`, `guidance-read-toggle.tsx`가 절차 목록·상세와 안내 확인 상태를 표시합니다.

`api.ts`는 TanStack Query로 목록과 상세를 캐시합니다. 기본 Mock 모드에서는 `src/mocks/mock-api.ts`를 호출하고, `VITE_USE_MOCK_API=false`에서는 공통 Axios로 다음 A07 요청을 보냅니다.

- `GET /api/procedures`
- `GET /api/procedures/{procedureId}`

API 응답의 선택 필드는 화면 타입으로 정규화합니다. ID 없는 목록 항목과 URL이 없는 공식 링크는 표시 대상에서 제외합니다. 절차 화면·A07 연결·정규화 구현과 통합 검증을 완료했습니다.
