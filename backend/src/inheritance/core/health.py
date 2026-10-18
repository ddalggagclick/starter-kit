# 책임: [통합] 최소 실행 환경의 프로세스 생존 신호.
# 구현할 기능: 인증 및 DB/모델 연결 없이 GET /health 응답.
# 코드 경계: 업무/API 경로와 분리하고 DB 준비 완료로 해석하지 않는다.
# 완료 기준: GET /health는 200 및 고정 상태를 반환한다.
from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health", summary="프로세스 생존 검사")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "inheritance-backend"}
