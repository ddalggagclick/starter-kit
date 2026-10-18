# 담당: [통합] | 책임: [통합] 백엔드 내부 공통 DTO 모음
# 구현할 기능: HTTP 응답 스키마와 분리; 상속 기능 간 공유할 최소 DTO만 공개
# 코드 경계: 내부 Domain/Port DTO만 둔다. HTTP JSON/Pydantic 응답은 API 담당자와 별도 협의한다.
# 완료 기준: 불필요한 부수효과 없이 패키지 import 가능.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
