<!--
담당: [A] | 책임: 초기·위험 질문, 절차 확인 상태, 동의 기반 체크리스트 저장.
구현할 기능: 로컬 상태·기기 저장·로그인 서버 저장 경로를 분리한다.
완료 기준: 저장 동의별로 기록 범위와 Mock/Backend 경로를 안내한다.
-->
# 체크리스트

## 화면과 상태

`landing-page.tsx`, `initial-questions-page.tsx`, `risk-questions.tsx`, `checklist-page.tsx`가 초기 질문부터 체크리스트까지의 화면을 구성합니다. 현재 질문·절차 확인 상태는 Zustand에서 관리합니다.

## 기기 저장

`checklist-storage.ts`와 `use-checklist-persistence.ts`가 체크리스트 저장 동의를 확인한 뒤 Dexie에 저장·복원합니다. 저장 동의와 대화 저장 동의는 분리되어 있으며 계정별 namespace를 사용합니다.

## 서버 저장

로그인 후 별도 서버 저장 동의를 받은 경우 `server-checklist-api.ts`가 A17 `GET`, `PUT`, `DELETE /api/me/checklist`를 호출합니다. `VITE_USE_MOCK_API=false`에서는 공통 Axios를 사용하고, 기본 Mock 모드에서는 Mock API를 사용합니다. Backend는 인증 서비스가 설정되면 A17 라우터를 등록합니다. 서버 저장은 기기 저장 기록과 자동 병합하지 않습니다.

`api.ts`는 현재 비어 있는 Axios 어댑터 파일입니다. 서버 체크리스트 요청은 `server-checklist-api.ts`가 담당합니다. 체크리스트 화면·기기 저장·서버 저장 구현과 통합 검증을 완료했습니다.
