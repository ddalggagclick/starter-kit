<!--
담당: [A] | 책임: GitHub 이슈 #40의 저장소 내 사본. 작업 1개 = 이슈 1개 = 커밋 1개 = PR 1개 규칙에 따른다.
원본: https://github.com/ddalggagclick/starter-kit/issues/40
-->
# [feat] 상속 관계·상속세·오류 제보 Mock (W-05·W-06·W-08) #40

- **GitHub 이슈:** https://github.com/ddalggagclick/starter-kit/issues/40
- **브랜치:** `40-feat-mock-general-info` (`38-feat-mock-conversations` 위에 쌓음)
- **PR:** base `38-feat-mock-conversations` · close #40 · #38 PR이 머지된 뒤 머지
- **순서:** Mock 이슈 14개 중 6번째
- **변경 파일:** `frontend/src/mocks/general-info.ts`, 이 문서

## 목표

W-05 내 상속 관계 알아보기, W-06 상속세 기본 안내, W-08 정보 오류 제보 Mock 모달에 쓸 문구를 만든다.
일반 설명이며 개인별 상속인 판정·세액 계산을 하지 않는다. W-08은 외부 Google Forms 주소가 정해지지 않아 실제 전송 없는 Mock 모달 문구만 둔다.

## 작업

- [x] `frontend/src/mocks/general-info.ts` 작성
  - RELATIONSHIP_GUIDE(상속 순위·배우자 일반 설명)
  - INHERITANCE_TAX_GUIDE(신고 기한·방법)
  - FEEDBACK_MOCK_COPY(준비 중·전송 안 됨 안내)
- [x] 이슈 문서 `frontend/docs/issues/` 작성

## 완료 조건

- `npx tsc -b`, `npx biome check src/mocks` 통과
- 모든 문구에 검수 전 Mock 표시
- 근거: 화면정의서 v1.4 06장(유지 화면), PRD 2-6-1·2-6-3·2-6-4

## 검증 메모

- import: `./wire-types`(#28)
- 작업 폴더 전체 기준 tsc·biome 통과. 이 커밋 단독 빌드는 따로 확인하지 않았다.
- 상속 순위·상속세 기한 문구는 B1 검수 전 일반 설명이다.
