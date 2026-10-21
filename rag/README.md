<!-- 책임: [D] RAG Parser의 형식별 요구사항과 Agentic Chunking 모델 설정을 안내한다.
구현할 기능: Parser 추가 요구사항과 청킹 공급자의 명시적 설정 방법을 기록한다.
완료 기준: 형식별 실행 조건과 청킹 모델 설정·오류 정책을 확인할 수 있다. -->
# RAG Parser 및 Agentic Chunking 모델 설정

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
