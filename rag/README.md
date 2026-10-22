<!-- 책임: [D] RAG Parser의 형식별 요구사항과 Agentic Chunking 모델 설정을 안내한다.
구현할 기능: Parser 추가 요구사항과 청킹 공급자의 명시적 설정 방법을 기록한다.
완료 기준: 형식별 실행 조건과 청킹 모델 설정·오류 정책을 확인할 수 있다. -->
# RAG Parser 및 Agentic Chunking 모델 설정

## RAG 단독 설치·배포 경로

RAG는 Backend 없이 `rag/pyproject.toml`만으로 설치할 수 있는 CLI 패키지이며, CLI 진입점은
`starter-rag`입니다. macOS/Linux에서는 저장소의 `rag/` 디렉터리에서 별도 가상환경을 만들고
설치합니다.

```bash
cd /path/to/starter-kit/rag
uv venv .venv
uv pip install --python .venv/bin/python .
.venv/bin/starter-rag status
```

이 독립 설치 경로는 `rag/pyproject.toml`의 버전 범위를 사용하며 별도 RAG lockfile은 없습니다.
저장소 개발 환경에서 루트 workspace lockfile을 재현하려면 저장소 루트에서 기존처럼
`uv run --project rag --locked starter-rag ...`를 사용합니다.

이 설치는 PostgreSQL 서버, pgvector 확장, 임베딩 모델 가중치를 설치하지 않습니다. DB와 모델은
각각 별도로 준비해야 합니다. 현재 이슈 #62의 RAG DB 어댑터는 로컬 `starter_rag_integration`만
허용하며, Supabase 운영 연결은 Backend의 SearchPort 통합 작업 범위입니다.

## 768차원 임베딩과 로컬 pgvector

문서 임베딩과 질의 임베딩은 `google/embeddinggemma-2` revision
`914f7f89142e33e77833254d9c9b90c3cef7303b`를 함께 사용하며 결과는 768차원입니다.
모델은 이미 로컬 Hugging Face 캐시에 있어야 하며, 실행 중 원격 다운로드는 하지 않습니다.

DB 연결은 `RAG_DATABASE_URL` 환경 변수로 전달합니다. 안전을 위해 URL은 로컬 호스트/Unix
소켓의 `starter_rag_integration` DB만 허용합니다. 기존 `postgres` DB와 Supabase URL은 거부됩니다.
예를 들어 로컬 Unix 소켓 연결은 다음 형태입니다.

```bash
export RAG_DATABASE_URL='postgresql+asyncpg://<local-user>@/starter_rag_integration?host=%2Ftmp'
```

별도 로컬 데이터베이스를 먼저 준비한 뒤, 아래 명령을 명시적으로 실행해 `vector` 확장과
`rag_test.chunks` 테이블을 생성합니다. 이 테이블은 `chunk_id TEXT PRIMARY KEY`와
`vector(768)`을 사용합니다. 앱/CLI 시작 때 자동 생성되거나 적재되지 않습니다.

```bash
createdb starter_rag_integration
uv run --project rag --locked starter-rag db-init
```

`index`는 입력 파일을 기존 Parser와 Agentic Chunker에 전달합니다. 따라서 기존 청킹 설정과
로컬 토크나이저가 필요합니다. 같은 `source-id`·`version`·파일 내용으로 다시 실행하면 기존
indexed/published 행을 그대로 유지합니다. 같은 버전의 내용 변경은 거부되므로 새 버전 ID를
사용하세요. `publish`는 완전한 indexed 버전만 게시하고, 새 버전 게시 시 이전 게시 버전을
같은 트랜잭션에서 `retired`로 전환합니다.

```bash
export RAG_CHUNKING_PROVIDER=ollama
export RAG_CHUNKING_MODEL=qwen3:4b-instruct
export RAG_CHUNKING_OLLAMA_BASE_URL=http://127.0.0.1:11434

uv run --project rag --locked starter-rag index \
  --file ./path/to/official-guide.xlsx \
  --tokenizer-path /path/to/local/tokenizer \
  --source-id official-guide \
  --version 2026-10 \
  --source-title '공식 안내자료 제목' \
  --source-url 'https://official.example.org/guide' \
  --publisher '발행기관' \
  --collection-id published-guides

uv run --project rag --locked starter-rag publish \
  --source-id official-guide --version 2026-10
uv run --project rag --locked starter-rag search \
  --query '상속 금융계좌 조회 방법' --top-k 3
```

`search` 기본 collection은 `published-guides`이고 합성 자료를 제외합니다. 테스트 자료에는
`--synthetic`을 주고 별도 collection ID를 사용하세요. 합성 자료는 `--allow-synthetic`을 명시한
로컬 테스트 검색에서만 노출됩니다. 합성 자료를 기본 `published-guides` collection에 게시할 수
없습니다. 법령 원문은 인덱싱하지 마세요.

`RAG_DATABASE_URL` 누락/허용되지 않은 DB, 잘못된 CLI 입력은 종료 코드 2입니다. DB·모델 연결,
임베딩 또는 저장 실패는 종료 코드 1이며, 상세 DB URL이나 비밀값은 출력하지 않습니다.

## Agentic Chunking 모델

RAG 청킹은 `RAG_CHUNKING_PROVIDER`로 공급자를 명시한다. 로컬 개발은 Ollama, 배포는 승인된 Gemini 모델을 사용한다. `APP_ENV`, `LLM_*`, `GEMINI_API_KEY`, `GROQ_API_KEY`로 공급자나 인증값을 선택하지 않으며 공급자 자동 전환도 하지 않는다.

### 로컬 개발: Ollama

```dotenv
RAG_CHUNKING_PROVIDER=ollama
RAG_CHUNKING_MODEL=qwen3:4b-instruct
RAG_CHUNKING_OLLAMA_BASE_URL=http://127.0.0.1:11434
```

`RAG_CHUNKING_OLLAMA_BASE_URL`은 생략할 수 있으며 기본값은 `http://127.0.0.1:11434`입니다. Ollama 서버와 모델은 별도로 준비해야 합니다. RAG는 Ollama를 설치하거나 모델을 내려받지 않습니다.

### 배포: Gemini

```dotenv
RAG_CHUNKING_PROVIDER=gemini
RAG_CHUNKING_MODEL=<배포에서 승인한 Gemini 모델 ID>
RAG_CHUNKING_GEMINI_API_KEY=<비밀 환경 변수>
```

배포 환경에서 승인된 모델 ID를 지정하고 API 키는 비밀 환경 변수로 주입합니다. 이 키는 `ChatGoogleGenerativeAI(api_key=...)`에 명시적으로 전달되며 초기화 오류와 청킹 fallback 메타데이터에서 감춥니다. RAG 전용 키가 없으면 설정 오류를 반환합니다.

Groq는 이번 연결 범위에 포함하지 않았습니다. 필요한 경우 별도 승인 후 RAG 직접 의존성과 전용 설정을 추가합니다.

내부 실행 경계는 `starter_rag.ingestion.service.chunk_document_with_config()`입니다. service는 `starter_rag.ingestion.chunking_model`에 RAG 설정과 모델 생성을 위임한 뒤, 반환된 모델을 기존 `chunk_document(model=...)`에 전달합니다. 두 모듈을 import하는 것만으로 모델 생성·네트워크 요청·인증값 검증은 일어나지 않습니다. 기존 외부 토큰 계산기를 그대로 전달해야 하며, 기본값이나 문자열 길이로 운영 토큰 수를 대체하지 않습니다.

```python
chunks = await chunk_document_with_config(
    structure,
    source_id=source_id,
    version=version,
    count_tokens=count_tokens,
)
```

공급자·모델 설정 누락, 지원하지 않는 공급자, 공급자와 형식이 맞지 않는 Gemini 모델 ID, 잘못된 Ollama URL은 모델 초기화 전 설정 오류로 처리합니다. Gemini 모델 이름의 형식만 로컬에서 검사할 수 있습니다. 해당 모델 ID의 실제 존재 여부와 API 키 유효성, Ollama 모델 사용 가능 여부는 외부 요청으로 확인되며, 실패 정보는 키를 감춘 fallback 메타데이터에 기록됩니다. SDK 초기화 오류도 자격값을 감춘 초기화 오류로 구분합니다.

일반 문서 그룹핑은 기존 최대 4회 시도와 결정적 fallback 정책을 따릅니다. HTTP 429는 같은 모델로 재시도하지 않으며 다른 공급자로 전환하지 않습니다. 표 입력은 행마다 청크를 만들고 LLM API를 호출하지 않습니다.

### CLI로 청킹 결과 확인하기

셸에 공급자 설정을 지정한 뒤 `chunk` 명령을 실행합니다. 다음 예시는 Ollama 설정과 기본 주소(`http://127.0.0.1:11434`)를 사용합니다.

```bash
RAG_CHUNKING_PROVIDER=ollama \
RAG_CHUNKING_MODEL=qwen3:4b-instruct \
uv run --locked starter-rag chunk \
  --file ./path/to/guide.pdf \
  --tokenizer-path /path/to/local/qwen3-tokenizer \
  --source-id guide-test \
  --version local
```

`--tokenizer-path`에는 `transformers.AutoTokenizer`가 읽을 수 있는 로컬 토크나이저 디렉터리나 이미 캐시된 Hugging Face 모델 ID를 지정합니다. CLI는 원격 다운로드를 하지 않습니다. Ollama의 `qwen3:4b-instruct` 태그 자체가 토크나이저 경로인 것은 아니므로, 같은 Qwen3 모델 계열의 Transformers 토크나이저 파일을 지정하세요.

토크나이저는 `target_tokens` 계산에만 사용되고, Agentic Chunking은 `RAG_CHUNKING_PROVIDER`로 선택한 채팅 모델이 수행합니다. 따라서 청킹 모델과 같은 계열의 토크나이저를 권장합니다. Gemini의 실제 토큰 수를 API에서 조회하지 않으므로 로컬 토크나이저의 수치는 추정치일 수 있습니다. XLSX만 입력하면 1행 1청크로 생성하며 채팅 모델은 호출하지 않습니다.

## Parser 형식과 의존성

현재 확인한 Docling 버전은 2.140.0입니다. Parser는 설치된 Docling의 `InputFormat` 전체를 변환기에 허용하고 `FormatToExtensions`에 등록된 확장자를 대소문자 구분 없이 검사합니다. `.dclg.xml`, `.tar.gz` 같은 복합 확장자도 처리합니다. 지원 목록은 설치 버전에 따라 달라질 수 있습니다.

현재 `docling` 의존성은 `docling-slim[standard]`을 설치합니다. 이 기본 구성에는 XLSX의 `openpyxl`, HTML의 BeautifulSoup, PDF의 `docling-parse`와 `pypdfium2`가 포함됩니다. 일반 HTML 변환에는 Playwright가 필요하지 않습니다. JavaScript 렌더링을 위한 HTML 변환만 `format-html-render` extra와 Playwright가 필요합니다.

아래 형식은 Parser에서 허용되지만, 일부는 추가 의존성·외부 런타임이 필요하고 일부는 입력별 추가 조건이 있습니다. 공식 extra가 이미 `standard` 구성에 포함된 의존성만 선언한다면 새 패키지는 설치되지 않습니다.

| 형식 | 추가 요구사항 |
|---|---|
| DOC, XLS, PPT, RTF | LibreOffice 런타임 |
| ODT, ODS, ODP | `docling-slim[format-opendocument]` (`odfdo`) |
| XML_XBRL | `docling-slim[format-xml-xbrl]` (`arelle-release`) |
| AUDIO | `docling-slim[format-audio]` 등 ASR 의존성과 ASR 모델 |
| VIDEO | `docling-slim[format-video]` 등 ASR 의존성, ASR 모델, `ffmpeg` 런타임 |
| IWORK_PAGES, IWORK_KEYNOTE, IWORK_NUMBERS | Docling의 공식 `format-iwork` extra를 사용할 수 있습니다. 이 extra의 `defusedxml`은 이미 `standard` 구성에 포함돼 있어 현재 환경에서는 새 패키지가 추가되지 않습니다. |
| EBCDIC | 입력 파일에 맞는 record layout |

잘못되었거나 잘린 HTML은 Docling이 복구해 성공 상태로 반환할 수 있습니다. XLSX/PDF처럼 모든 불완전 입력이 변환 오류로 분류되는 것은 아닙니다.
