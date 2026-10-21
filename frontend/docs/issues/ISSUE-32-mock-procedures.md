<!--
담당: [A] | 책임: GitHub 이슈 #32의 저장소 내 사본. 작업 1개 = 이슈 1개 = 커밋 1개 = PR 1개 규칙에 따른다.
원본: https://github.com/ddalggagclick/starter-kit/issues/32
-->
# [feat] 절차 8개 목록·상세·기한 꼬리표 Mock (A07) #32

- **GitHub 이슈:** https://github.com/ddalggagclick/starter-kit/issues/32
- **브랜치:** `32-feat-mock-procedures` (`28-feat-mock-wire-types` 위에 쌓음)
- **PR:** base `28-feat-mock-wire-types` · close #32 · #28 PR이 머지된 뒤 머지
- **순서:** Mock 이슈 14개 중 2번째
- **변경 파일:** `frontend/src/mocks/procedures.ts`, 이 문서

## 목표

W-02·W-03·W-04·K-04 화면과 A07 절차 API Mock이 함께 쓸 8개 절차(p01~p08) 목록·상세·기한 꼬리표 데이터를 만든다.
절차 이름·문구·기한은 검수 전 예시이며, p01~p08과 절차 이름 대응(D6)은 Mock 배정이다. 공식 링크는 기관 대표 주소만 쓴다.

## 작업

- [x] `frontend/src/mocks/procedures.ts` 작성 (PROCEDURE_IDS, MOCK_PROCEDURE_SUMMARIES, MOCK_DEADLINE_TAGS, MOCK_PROCEDURE_DETAILS, findProcedureName)
- [x] 상세는 openapi ProcedureDetail 필드(action·deadline·risk·agency·documents·methods·exceptions·contacts·officialLinks·relatedProcedureIds 0~3개)를 따름
- [x] 이슈 문서 `frontend/docs/issues/` 작성

## 완료 조건

- `npx tsc -b`, `npx biome check src/mocks` 통과
- 8개 절차 모두 공식 링크 1개 이상, 관련 절차 3개 이하 (mock-api.test.ts에서 검사, Mock 이슈 8번째)
- 근거: openapi A07, 화면정의서 v1.4 06·07장(W-04 B 접기형), 부록3

## 검증 메모

- import: `@/shared/contracts/domain`(tracked), `./wire-types`(#28)
- 작업 폴더 전체 기준 tsc·biome 통과. 이 커밋 단독 빌드는 따로 확인하지 않았다.
