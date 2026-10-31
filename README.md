<!-- 책임: [통합] 상속길잡이 스타터킷의 최상위 길잡이.
구현할 기능: bootstrap 프로필 선택, 설치, 실행 진입점을 루트 기준으로 안내한다.
완료 기준: RUN_FIRST.md와 프로필·명령·상태가 일치하고 파일 소유 경계 문서를 연결한다. -->
# 상속길잡이 × AI 스타터킷

상속 절차 안내 웹앱과 독립 LLM·RAG CLI를 개발하는 스타터킷입니다.

## 시작하기

저장소 루트에서 실행해 사용할 프로필을 고릅니다.

```bash
bash scripts/bootstrap.sh
```

| 프로필 | 포함 범위 |
|---|---|
| 상속길잡이 전체 | Backend, Frontend, LLM, RAG |
| LLM CLI만 | LLM 패키지와 명령줄 도구 |
| RAG CLI만 | 문서 색인·검색 명령줄 도구 |

모든 프로필은 Python 3.13과 `uv`가 필요합니다. 전체 프로필은 Node.js 24.22.1 이상과 `npm`도 필요합니다.

## 전체 앱 실행

Backend와 Frontend를 각각 별도 터미널에서 실행합니다.

```bash
.venv/bin/python scripts/local_env.py run uv run uvicorn app_entry:app --app-dir backend --port 8000
npm --prefix frontend run dev
```

- Frontend: <http://localhost:5173/>
- Backend 헬스 확인: <http://127.0.0.1:8000/health>

Frontend를 실제 Backend에 연결하려면 `frontend/.env.development`에 아래 값을 설정하고 개발 서버를 다시 시작합니다.

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK_API=false
```

기능 구현과 통합 검증은 완료됐습니다. 전체 아키텍처와 ERD는 최종 승인되지 않았습니다.

## 자세한 안내

- 설치·설정·프로필별 실행: [`RUN_FIRST.md`](RUN_FIRST.md)
- RAG CLI 사용법: [`rag/README.md`](rag/README.md)
- 폴더 책임과 파일 소유권: [`docs/PROJECT_STRUCTURE_GUIDE.md`](docs/PROJECT_STRUCTURE_GUIDE.md)
