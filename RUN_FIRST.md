<!-- 책임: [통합] v2.10 첫 설치/실행 2+4 명령을 단일 루트에서 재현하는 빠른 안내.
구현할 기능: 루트에서 Python/Frontend 설치 및 Backend/Frontend/LLM/RAG 최소 진입점을 각각 실행한다.
완료 기준: 아래 2개 설치 후 4개 실행 명령이 별도의 터미널에서 각각 기동/종료 코드 0으로 동작한다. -->
# v2.10 — 설치 2개, 실행 4개

**모든 명령을 압축을 푼 `starter-kit/` 폴더에서 실행하세요.** Python **3.13**, `uv`, Node.js **24**, `npm`, 인터넷 연결이 미리 준비되어 있어야 합니다.

## 최초 설치: 딱 2개

```bash
uv sync
npm --prefix frontend install
```

`uv sync`는 Backend, LLM, RAG 및 Docling, EmbeddingGemma 관련 라이브러리를 함께 설치합니다. `npm --prefix frontend install`은 React/Vite/shadcn 호환 라이브러리를 설치합니다. **첫 설치는 네트워크/디스크 여유에 따라 오래 걸릴 수 있습니다.** `uv.lock`, `frontend/package-lock.json`은 최초 성공 후 커밋하세요.

## 실행: 딱 4개 (각각 다른 터미널, 모두 루트에서)

```bash
uv run uvicorn inheritance.main:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
uv run starter-llm status
uv run starter-rag status
```

카카오→웹 인계 토큰은 서버 메모리에만 저장되므로 Backend는 uvicorn 워커 1개로 실행합니다(`--workers` 옵션을 늘리지 않습니다).

- **Backend**: 실행 상태로 유지됩니다. 브라우저에서 `http://127.0.0.1:8000/health` → `{"status":"ok","service":"inheritance-backend"}`.
- **Frontend**: 실행 상태로 유지됩니다. `http://localhost:5173/` 열기 → 화면 확인 후 **서버 상태 확인** 버튼 클릭. (실제 Vite 출력 주소가 우선.)
- **LLM**: `uv run starter-llm status` — JSON에 `"status": "implemented"`, 공급자·전환 설정, 키 설정 여부(값은 출력 안 함). 외부 호출 없음. 실제 생성은 `uv run starter-llm generate --prompt "안녕하세요"`(키 필요, 종료 코드 0/2/3/4/5/6/7).
- **RAG**: JSON에 `"status": "contract-only"`, `"searchImplemented": false` 출력 후 종료(정상). Docling/pgvector 실연동 아님.

**참고**: Windows의 PowerShell에서도 네 명령은 같은 형태로 사용합니다. 포트 8000/5173을 이미 다른 프로세스가 사용하면 충돌할 수 있습니다. `uv`와 `npm` 명령을 실행할 수 없는 상태라면 먼저 프로그램 설치/PATH를 점검합니다.

### 별도 추가 확인(필수 네 명령에 포함하지 않음)

```bash
npm --prefix frontend run build
uv run python -m unittest discover -s tests -v
python scripts/verify_contracts.py
```

이 단계는 **개발 환경 부팅 확인**일 뿐입니다. 회원가입, 로그인, Supabase 연결, Gemini/Groq 호출, RAG 적재/검색은 아직 구현되지 않았습니다. 전체 아키텍처 및 ERD 최종 승인을 임의로 선언하지 않습니다.
