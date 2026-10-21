<!--
담당: [A] | 책임: GitHub 이슈 #38의 저장소 내 사본. 작업 1개 = 이슈 1개 = 커밋 1개 = PR 1개 규칙에 따른다.
원본: https://github.com/ddalggagclick/starter-kit/issues/38
-->
# [feat] 이전 대화·새 대화·나가기 확인 문구 Mock (S8·S10·S11) #38

- **GitHub 이슈:** https://github.com/ddalggagclick/starter-kit/issues/38
- **브랜치:** `38-feat-mock-conversations` (`36-feat-mock-ai-stream` 위에 쌓음)
- **PR:** base `36-feat-mock-ai-stream` · close #38 · #36 PR이 머지된 뒤 머지
- **순서:** Mock 이슈 14개 중 5번째
- **변경 파일:** `frontend/src/mocks/conversations.ts`, 이 문서

## 목표

W-07 S8 새 대화, S10 이전 대화 목록, S11 저장 안 된 대화 나가기 확인 화면용 Mock 데이터와 문구를 만든다.
실제 Dexie 저장이 아니며, 대화 목록 상한·제목 길이는 검증 필요(P02)라 Mock 값이다.

## 작업

- [x] `frontend/src/mocks/conversations.ts` 작성
  - 이전 대화 2건(10/14·10/12)
  - 제목 = 첫 질문 앞부분(Mock 20자)
  - 빈 목록 문구, S11 이탈 확인 문구·버튼 3개, S8 보관 안내 문구
- [x] 이슈 문서 `frontend/docs/issues/` 작성

## 완료 조건

- `npx tsc -b`, `npx biome check src/mocks` 통과
- 근거: 화면정의서 v1.4 08장 S8·S10·S11, 15장 ② A안, 부록4 (D-04·D-05·D-11·D-14)

## 검증 메모

- import: `./wire-types`(#28)
- 작업 폴더 전체 기준 tsc·biome 통과. 이 커밋 단독 빌드는 따로 확인하지 않았다.
