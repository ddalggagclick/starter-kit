<!--
담당: [A] | 책임: GitHub 이슈 #28의 저장소 내 사본. 작업 1개 = 이슈 1개 = 커밋 1개 기록 규칙에 따른다.
원본: https://github.com/ddalggagclick/starter-kit/issues/28
-->
# [feat] Mock 전용 wire 타입 추가 (openapi 0.2.0-draft) #28

- **GitHub 이슈:** https://github.com/ddalggagclick/starter-kit/issues/28
- **브랜치:** `28-feat-mock-wire-types` (dev에서 분기)
- **PR:** base `dev` · `Closes #28` · Mock 이슈 14개 중 이후 PR들이 이 브랜치 위에 순서대로 쌓인다
- **소급 기록:** 2026-10-21 Mock 작업을 이슈 14개로 나눈 것 중 1번째
- **변경 파일:** `frontend/src/mocks/wire-types.ts`, 이 문서

## 목표

화면정의서 v1.4 기반 Mock이 API 계약과 같은 필드·enum을 쓰도록, openapi.yaml 0.2.0-draft 스키마를 옮긴 Mock 전용 TypeScript 타입을 만든다.
승인된 생성 타입(shared/api/schema.d.ts)을 대신하지 않으며 Mock 밖에서 import하지 않는다.

## 작업

- [x] `frontend/src/mocks/wire-types.ts` 작성 (Error, HandoffPayload, ProcedureSummary/Detail, AskAiRequest, SSE status/result/error, LoginResponse, ChecklistSaved)
- [x] 필드 이름 camelCase·enum 값을 openapi.yaml과 대조
- [x] 이슈 문서 `frontend/docs/issues/` 작성

## 완료 조건

- `npx tsc -b` 통과
- `npx biome check src/mocks` 통과
- 근거: docs/contracts/openapi.yaml 0.2.0-draft (A04·A05·A07·A08·A13·A17)

## 검증 메모

- 작업 폴더 전체(Mock 14개 파일 포함) 기준으로 `tsc -b`, `biome check src/mocks`가 통과했다.
- 이 커밋만 따로 떼어 낸 상태의 빌드는 확인하지 않았다. 이 파일은 tracked 파일인 `shared/contracts/domain.ts`만 import한다.
- pull 이후 openapi.yaml(`b76fcb5`)은 표기 변경과 504 "D2 확정" 문구뿐이어서 이 타입에 영향이 없다.
