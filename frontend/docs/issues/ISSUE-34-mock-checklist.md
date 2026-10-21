<!--
담당: [A] | 책임: GitHub 이슈 #34의 저장소 내 사본. 작업 1개 = 이슈 1개 = 커밋 1개 = PR 1개 규칙에 따른다.
원본: https://github.com/ddalggagclick/starter-kit/issues/34
-->
# [feat] 초기 3문항·위험 질문·공통 경고·저장 상태 Mock #34

- **GitHub 이슈:** https://github.com/ddalggagclick/starter-kit/issues/34
- **브랜치:** `34-feat-mock-checklist` (`32-feat-mock-procedures` 위에 쌓음)
- **PR:** base `32-feat-mock-procedures` · close #34 · #32 PR이 머지된 뒤 머지
- **순서:** Mock 이슈 14개 중 3번째
- **변경 파일:** `frontend/src/mocks/checklist.ts`, 이 문서

## 목표

W-01·W-02(R1~R3·P1·C1)·K-01~K-04 화면 확인용 체크리스트 Mock 데이터를 만든다.
위험 안내 문구는 화면정의서 그림에 나온 문장만 승인 문구로 두고, 문구가 없는 답은 공통 위험 경고만 보여준다(15장 ① A안). 새 안내 문장을 만들지 않는다.

## 작업

- [x] `frontend/src/mocks/checklist.ts` 작성: 공통 위험 경고·면책 문구, W-00 문구, 초기 3문항 선택지, 위험 질문 3개(W01~W03)와 승인 문구, findRiskGuidance, 저장 상태 3가지 문구, 동의·삭제 문구, W-01 진입 상태 E0~E3, 진입 시나리오 direct·kakao·restored
- [x] 이슈 문서 `frontend/docs/issues/` 작성

## 완료 조건

- `npx tsc -b`, `npx biome check src/mocks` 통과
- 승인 문구 없는 답(예: 채무 없음, 본인 신청 모름)은 null 반환 (mock-api.test.ts에서 검사, Mock 이슈 8번째)
- 근거: 화면정의서 v1.4 04·05·09·10·15장, 부록1~3·5 (Q70·Q71·Q82 A·D-03·D-08·D-09·D-10)

## 검증 메모

- import: `@/shared/contracts/domain`, `@/shared/contracts/ui`(둘 다 tracked)
- 작업 폴더 전체 기준 tsc·biome 통과. 이 커밋 단독 빌드는 따로 확인하지 않았다.
