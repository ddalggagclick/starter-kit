<!--
담당: [A] | 책임: GitHub 이슈 #42의 저장소 내 사본. 작업 1개 = 이슈 1개 = 커밋 1개 = PR 1개 규칙에 따른다.
원본: https://github.com/ddalggagclick/starter-kit/issues/42
-->
# [feat] 비동기 Mock API 함수 (A05·A07·A08·A11~A17) #42

- **GitHub 이슈:** https://github.com/ddalggagclick/starter-kit/issues/42
- **브랜치:** `42-feat-mock-api` (`40-feat-mock-general-info` 위에 쌓음)
- **PR:** base `40-feat-mock-general-info` · close #42 · #40 PR이 머지된 뒤 머지
- **순서:** Mock 이슈 14개 중 7번째
- **변경 파일:** `frontend/src/mocks/mock-api.ts`, 이 문서

## 목표

openapi.yaml 0.2.0-draft 경로를 흉내 내는 비동기 Mock API 함수를 만들어, 이후 화면이 실제 Backend 없이 정상·실패·취소 상태를 확인할 수 있게 한다.
공통 Axios 인스턴스를 거치지 않으며 실제 연동 결과로 보고하지 않는다. 토큰·비밀번호를 브라우저 저장소에 쓰지 않는다.

## 작업

- [x] `frontend/src/mocks/mock-api.ts` 작성
  - 지연·AbortSignal 취소·MockHttpError(status·body)
  - A05 exchangeHandoff: 유효 토큰 1회만 성공, 나머지는 같은 400 HANDOFF_INVALID
  - A07 listProcedures·getProcedure(404)
  - A08 askAi(ai-stream 위임)
  - A11 signup(422·409), A13 login(401, 5번 실패 후 429), A14 logout, 재전송·재설정 202
  - A17 get·put·deleteMyChecklist(401·403)
  - resetMockApiState
- [x] 이슈 문서 `frontend/docs/issues/` 작성

## 완료 조건

- `npx tsc -b`, `npx biome check src/mocks` 통과
- 동작 검증은 mock-api.test.ts(Mock 이슈 8번째)
- 근거: openapi A05·A07·A08·A11~A17, 화면정의서 v1.4 부록5 W-09, D-08

## 검증 메모

- import: `@/shared/contracts/domain`(tracked), `./ai-stream`(#36), `./procedures`(#32), `./wire-types`(#28)
- 404 NOT_FOUND·409 EMAIL_TAKEN 코드 이름은 팀 오류 목록에 없어 openapi상 제안 상태다.
- 확인용 값: Handoff `mock-handoff-valid`, 로그인 `demo@example.com` / `mockpass1`(Mock 계정, 실제 계정 아님)
- 작업 폴더 전체 기준 tsc·biome 통과. 이 커밋 단독 빌드는 따로 확인하지 않았다.
