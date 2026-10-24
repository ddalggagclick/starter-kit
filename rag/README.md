<!-- 책임: [D] RAG 독립 CLI와 Parser·청킹·pgvector 사용법을 안내한다.
구현할 기능: 명령별 용도, 실행 조건, 데이터베이스 영향과 모델 설정을 기록한다.
완료 기준: 검증·파싱·색인·게시·검색·평가 CLI 흐름을 재현할 수 있다. -->
# RAG CLI 사용 설명서

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
각각 별도로 준비해야 합니다. 기본 DB 프로필은 로컬 `starter_rag_integration`이며, Supabase는
`--db-profile supabase`와 승인된 Session Pooler URL·collection ID를 명시할 때만 사용합니다.

## CLI 명령 목록

전체 도움말은 `starter-rag --help`, 명령별 옵션은 `starter-rag <명령> --help`로 확인합니다.
CLI는 사용자가 명시적으로 호출한 작업만 실행하며, 앱 시작 때 파싱·색인·게시하지 않습니다.

| 명령 | 용도 | DB·모델 동작 |
|---|---|---|
| `starter-rag status` | 구현 상태와 `RAG_DATABASE_URL` 설정 유무를 표시합니다. 연결 상태는 검사하지 않습니다. | DB에 연결하지 않습니다. |
| `starter-rag parse PATH` | Docling 문서 구조와 원문 위치를 JSON으로 출력합니다. | DB를 사용하지 않습니다. |
| `starter-rag chunk PATH` | 파싱·청킹 결과와 처리 상태를 JSON으로 출력합니다. `--source-id`, `--version`(기본 `cli-test`), `--target-tokens`(기본 512)을 선택할 수 있습니다. | DB에 쓰지 않습니다. 일반 문서는 청킹 모델을 사용할 수 있고 XLSX 표 행은 결정적으로 처리합니다. |
| `starter-rag db-init` | 승인된 로컬 DB에 `vector` 확장과 `rag_test.chunks` 테이블을 준비합니다. | 스키마를 변경합니다. |
| `starter-rag index PATH` | 일반 자료는 `--source-id`, `--version`, `--source-title`, `--publisher`가 필요합니다. `--source-url`은 선택이며 HTTPS만 허용합니다. `--type source-v2`는 Source_v2 전용 색인을 실행합니다. `--target-tokens` 기본값은 512입니다. | DB에 색인하지만 게시하지 않습니다. 일반 기본 collection은 `published-guides`, Source_v2는 `rag-test-source-v2-e2e`입니다. |
| `starter-rag publish --source-id ID --version VERSION` | 기존 단건 게시 계약입니다. `--from-index-result PATH`는 index JSON의 모든 Source Unit을 검증한 뒤 배치 게시합니다. | 게시 상태를 변경합니다. Source Unit마다 원자 전환하며 배치 전체는 원자적이지 않습니다. 기본 collection은 `published-guides`입니다. |
| `starter-rag search "QUERY"` | 게시된 자료를 검색하고 기존 Evidence JSON을 반환합니다. `--top-k` 허용 범위는 1–10, 기본값은 3입니다. `--collection-id`, `--allow-synthetic`을 선택할 수 있습니다. | 게시 자료를 읽고 질의 임베딩을 만듭니다. 기본 collection은 `published-guides`, 합성 자료는 기본 검색에서 제외됩니다. |
| `starter-rag check PATH` | Source_v2 승인 상태, 필수값, URL 정책, 원본 행 참조와 31개 Unit 기준을 확인합니다. `--rows`를 추가하면 Docling 결과와 원본 XLSX 행의 일대일 대응도 확인합니다. | DB에 쓰지 않습니다. 비표시 내부 URL은 출력하지 않으며 결정적 `table_row` 청킹에서 모델 호출은 0회입니다. |
| `starter-rag test` | Golden Truth v1.2 기반 26문항 검색 품질 평가를 실행합니다. `--dataset`, `--out`, `--mode`(`clarified`/`title`, 기본 `clarified`), `--group`(`all`/`direct`/`partial`/`safety_context`, 기본 `all`)을 지원합니다. | `--validate-only`는 DB를 사용하지 않습니다. 실제 평가는 검색만 하며 DB를 수정하지 않습니다. |

일반 사용 명령은 `status`, `parse`, `chunk`, `db-init`, `index`, `publish`, `search`의 7개이고, 검증·평가
명령은 `check`, `test`의 2개입니다. 토크나이저 경로는 `--tokenizer-path`가 우선하며, 없으면
`RAG_TOKENIZER_PATH` 환경변수를 사용합니다. 어느 경로도 설정되지 않으면 명확한 오류를 반환하며
토크나이저를 내려받거나 다른 모델로 바꾸지 않습니다.

일반·Source_v2 `index` 모두 색인만 수행하며 `publish`를 별도로 호출해야 검색됩니다. 합성 자료는
별도 collection에 `--synthetic`으로 색인하고, 검색할 때 `--allow-synthetic`을 지정해야 합니다.
Source_v2의 URL 없는 Unit도 게시·검색할 수 있으며 Evidence에는 URL 외의 출처·버전·본문·위치·점수가
반환됩니다.

## Fork 개발자 재현 절차

### 1. 환경 준비

Python 3.13과 `uv`를 준비합니다.

### 2. RAG 설치

아래 workspace 명령은 저장소 루트에서 실행합니다. 독립 설치를 선택했다면 이후 `uv run` 명령 대신
`rag/.venv/bin/starter-rag` 실행 파일을 사용합니다.

```bash
uv sync
uv run --project rag --locked starter-rag status
```

독립 설치를 선택하면 `rag/`에서 별도 가상환경에 설치합니다.

```bash
cd /path/to/starter-kit/rag
uv venv .venv
uv pip install --python .venv/bin/python .
.venv/bin/starter-rag status
```

### 3. 로컬 테스트 환경변수 설정

아래 예시는 로컬 DB와 로컬 토크나이저를 사용합니다. `.env`는 자동으로 읽히지 않으므로 셸에서
환경변수를 설정합니다.

```bash
export RAG_DATABASE_URL='postgresql+asyncpg://<local-user>@/starter_rag_integration?host=%2Ftmp'
export RAG_TOKENIZER_PATH=/path/to/local/tokenizer
export RAG_CHUNKING_PROVIDER=ollama
export RAG_CHUNKING_MODEL=qwen3:4b-instruct
export RAG_CHUNKING_OLLAMA_BASE_URL=http://127.0.0.1:11434
```

로컬 DB가 준비되지 않은 경우에만 `starter-rag db-init`으로 로컬 테스트 스키마를 준비합니다.
이 명령은 운영 프로필에서 지원되지 않으며 운영 DB 준비 절차로 사용하지 않습니다.

### 4. Source Unit 검증

검수한 Source_v2 파일의 승인 상태와 행 대응을 확인합니다. `--rows`는 로컬 토크나이저가 필요하며
DB에 쓰지 않습니다.

```bash
SOURCE_XLSX=/path/to/reviewed/Source_v2.xlsx
uv run --project rag --locked starter-rag check "$SOURCE_XLSX"
uv run --project rag --locked starter-rag check "$SOURCE_XLSX" --rows
```

### 5. 색인

검증 후 색인 결과를 표준 출력에서 JSON 파일로 저장합니다. 색인은 DB에 색인 상태를 저장하지만
게시하지 않습니다.

```bash
uv run --project rag --locked starter-rag index "$SOURCE_XLSX" \
  --type source-v2 --db-profile local \
  --collection-id rag-test-source-v2-e2e \
  > source-v2-index-result.json
uv run --project rag --locked python -m json.tool source-v2-index-result.json
```

### 6. 검토 후 배치 게시

JSON을 검토한 관리자가 명시적으로 게시 명령을 실행합니다. JSON의 Source ID·버전·색인 상태만
믿지 않고, CLI는 게시 전에 DB collection과 실제 버전 상태도 확인합니다.

```bash
uv run --project rag --locked starter-rag publish \
  --from-index-result source-v2-index-result.json \
  --db-profile local \
  --collection-id rag-test-source-v2-e2e \
  > source-v2-publication-result.json
```

성공한 항목은 `published`, 이미 게시된 동일 버전은 `already_published`로 출력됩니다. 다른 버전이
현재 게시 중이면 SHA-256 버전만으로 최신성을 판정할 수 없어 기본적으로 해당 항목을 거부합니다.
검수자가 새 버전을 대체 대상으로 승인한 경우에만 `--allow-version-replacement`를 추가하세요.
이 옵션은 기존 게시 버전을 `retired`로 전환합니다.

Source_v2 외 `standard`와 `mapped-xlsx`의 기존 index 결과도 지원합니다. Standard는 단일 결과 객체,
Source_v2와 mapped-xlsx는 `outcomes` 배열을 입력으로 사용합니다. mapped-xlsx는 예시 매핑 파일을
Fork의 데이터 구조에 맞게 검토한 뒤 색인합니다.

```bash
uv run --project rag --locked starter-rag index ./path/to/guide.pdf \
  --source-id guide-001 \
  --version "$(shasum -a 256 ./path/to/guide.pdf | awk '{print $1}')" \
  --source-title '공식 안내자료' --publisher '발행기관' \
  --collection-id published-guides > guide-index-result.json
uv run --project rag --locked starter-rag publish \
  --from-index-result guide-index-result.json --collection-id published-guides \
  > guide-publication-result.json

uv run --project rag --locked starter-rag index ./path/to/guides.xlsx \
  --type mapped-xlsx --mapping rag/examples/source_v2_mapping.json \
  --collection-id local-guides --tokenizer-path "$RAG_TOKENIZER_PATH" \
  > mapped-index-result.json
uv run --project rag --locked starter-rag publish \
  --from-index-result mapped-index-result.json --collection-id local-guides \
  > mapped-publication-result.json
```

각 Source Unit은 별도 트랜잭션으로 처리되므로 배치 중 일부가 실패할 수 있습니다. 실패가 있으면
종료 코드는 1이고 JSON 결과의 `items`에 Source ID·버전·실패 항목이 표시됩니다. 수정 후 같은
index 결과로 재실행하면 이미 게시된 동일 버전은 건너뛰고 나머지를 재검증합니다. 입력·collection
불일치는 DB 쓰기 전에 종료 코드 2로 거부됩니다. 연결 장애가 게시 중 확인되면 남은 항목은
`not_attempted`로 남습니다. 결과 JSON에는 처리 총건수, 게시, 건너뜀, 실패, 미시도 건수가 있습니다.

### 7. 게시 결과 검색

```bash
uv run --project rag --locked starter-rag search '사망신고 절차' \
  --collection-id rag-test-source-v2-e2e --top-k 3
```

검색은 `published` 상태만 반환합니다. 색인 성공만으로 검색에 노출되지 않습니다.

### 8. 오류 확인 및 복구

종료 코드 2는 입력 JSON·옵션·collection 불일치 또는 DB 프로필 설정 오류입니다. 입력과 환경변수를
고친 뒤 다시 실행합니다. 종료 코드 1은 DB 오류나 항목별 게시 실패입니다. 저장한 publication
결과의 `items`에서 실패 Source ID·버전을 확인하고, `not_attempted` 항목은 DB 복구 후 같은 index
결과 파일로 다시 실행합니다. 게시 여부를 확인할 수 없는 연결 장애 메시지가 있으면 재실행 전에
해당 Source ID·버전의 DB 상태를 확인합니다.

### 운영 Supabase 게시

운영 경로는 로컬 테스트와 별개입니다. 운영 담당자가 승인한 Session Pooler 연결정보와 collection
ID를 비밀 환경변수로 설정하고, 해당 collection을 명시합니다. Supabase 대상에는 `db-init`이나
자동 마이그레이션을 실행하지 않습니다.

```bash
export DATABASE_URL='<approved Supabase Session Pooler URL on port 5432>'
export RAG_DB_SCHEMA=rag
export RAG_VECTOR_TABLE=chunks
export RAG_COLLECTION_ID='<approved collection ID>'
export RAG_TOKENIZER_PATH=/path/to/local/tokenizer

uv run --project rag --locked starter-rag index ./path/to/reviewed.xlsx \
  --type mapped-xlsx --mapping rag/examples/source_v2_mapping.json \
  --db-profile supabase --collection-id "$RAG_COLLECTION_ID" \
  --tokenizer-path "$RAG_TOKENIZER_PATH" > reviewed-index-result.json
# JSON을 검토하고 별도로 승인한 뒤에만 다음 명령을 실행합니다.
uv run --project rag --locked starter-rag publish \
  --from-index-result reviewed-index-result.json \
  --db-profile supabase --collection-id "$RAG_COLLECTION_ID" \
  > reviewed-publication-result.json
```

Supabase 색인·게시 명령은 명시적 DB 프로필, `DATABASE_URL`, `RAG_DB_SCHEMA=rag`,
`RAG_VECTOR_TABLE=chunks`, `RAG_COLLECTION_ID` 일치를 요구합니다. 이 설명은 실제 운영 게시를
승인하지 않으며, 운영 실행은 별도 승인을 받아야 합니다.

성공 종료 코드는 `0`, 잘못된 옵션·입력 또는 허용되지 않은 DB 설정은 `2`, DB·모델·임베딩·저장 중
실패는 `1`입니다. 오류 출력은 DB URL·비밀번호·토큰을 표시하지 않습니다.

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
  ./path/to/official-guide.xlsx \
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
  '상속 금융계좌 조회 방법' --top-k 3
```

`search` 기본 collection은 `published-guides`이고 합성 자료를 제외합니다. 테스트 자료에는
`--synthetic`을 주고 별도 collection ID를 사용하세요. 합성 자료는 `--allow-synthetic`을 명시한
로컬 테스트 검색에서만 노출됩니다. 합성 자료를 기본 `published-guides` collection에 게시할 수
없습니다. 법령 원문은 인덱싱하지 마세요.

`RAG_DATABASE_URL` 누락/허용되지 않은 DB, 잘못된 CLI 입력은 종료 코드 2입니다. DB·모델 연결,
임베딩 또는 저장 실패는 종료 코드 1이며, 상세 DB URL이나 비밀값은 출력하지 않습니다.

## Source_v2 관리자 CLI

Source_v2 원본 검증과 Docling 행 검증은 DB를 변경하지 않습니다. 색인과 게시는 별도 명령으로
실행합니다. 31개 Unit의 게시에는 `index` JSON을 검토한 뒤 `--from-index-result`를 사용합니다.

```bash
export RAG_TOKENIZER_PATH=/path/to/local/tokenizer

uv run --project rag --locked starter-rag check ./rag/data/Source_v2.xlsx
uv run --project rag --locked starter-rag check ./rag/data/Source_v2.xlsx --rows

uv run --project rag --locked starter-rag index \
  ./rag/data/Source_v2.xlsx --type source-v2 \
  --collection-id rag-test-source-v2-e2e \
  > source-v2-index-result.json

uv run --project rag --locked starter-rag publish \
  --from-index-result source-v2-index-result.json \
  --collection-id rag-test-source-v2-e2e

uv run --project rag --locked starter-rag search \
  '사망신고 절차' --top-k 3 \
  --collection-id rag-test-source-v2-e2e

uv run --project rag --locked starter-rag test --validate-only
uv run --project rag --locked starter-rag test --mode clarified
```

검증 기준은 승인 Unit 31건, 화면 표시 허용 16건, 화면 표시 비허용 15건, 실제 URL 없음 7건입니다.
비표시 URL은 Evidence에 포함하지 않습니다. Golden Truth 평가는 26개 질문과 38개 검증 라벨을
확인한 뒤 로컬 검색 결과를 평가하며 DB를 수정하지 않습니다. `--dataset`, `--group`, `--out`,
`--mode title`로 입력과 평가 범위를 고정할 수 있습니다.

26문항 실측은 `clarified` Hit@3 1.000 / Recall@3 0.865385, `title` Hit@3 0.692308 /
Recall@3 0.615385입니다. 두 모드 모두 정리 전과 같은 결과입니다. 작업 기준에 적힌 `clarified`
Recall@3 0.884615와는 차이가 있어, 평가 정의가 확인될 때까지 실제 측정값을 기록합니다.

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
  ./path/to/guide.pdf \
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

## 범용 XLSX 행 매핑 / Supabase 운영 경로

XLSX 검수·색인은 기존 RAG CLI에서 실행한다. `mapped-xlsx`는 헤더 이름과
식별자 직렬화 규칙을 JSON 구성으로 받으며, 상속 관련 상수는 범용 로직에 없다.
기존 `source-v2` 모드는 기존 호출자·평가 테스트의 호환성을 위해 유지한다.

- 범용 예제: `rag/examples/source_v2_mapping.json` (특정 데이터셋 규칙은 코드가 아닌 구성 파일)
- 새로운 도메인은 이 파일을 복사하고 `sheet`, `fields`, `projection`,
  `boolean_fields`, `split_fields`, `approval`, `docling`을 해당 데이터에 맞게 작성한다.
- `--db-profile local` (기본): `RAG_DATABASE_URL`을 통한 기존 로컬 연결만 허용한다.
- `--db-profile supabase`: 명시적 `DATABASE_URL` (Supabase Session Pooler:5432),
  `RAG_DB_SCHEMA=rag`, `RAG_VECTOR_TABLE=chunks`, `RAG_COLLECTION_ID`를 요구한다.
  `.env`는 자동 로드하지 않으며 실행 셸이 공급한다. `db-init`은 로컬 전용이다.
- pgvector가 이미 `extensions` 스키마에 설치된 이후에만 Alembic을 명시적으로 실행한다.
  서버 시작 시 DDL/색인/게시를 실행하지 않는다.

```bash
# 1. 명시적 Alembic 준비 (DB 작업 승인 후에만; 예시)
uv run alembic -c backend/alembic.ini upgrade head --sql   # 먼저 SQL 검토
# uv run alembic -c backend/alembic.ini upgrade head        # 별도 운영 DB 승인 후

# 2. 운영 색인. RAG_TOKENIZER_PATH 또는 --tokenizer-path를 지정한다.
uv run --project rag --locked starter-rag index Source_v2.xlsx \
  --type mapped-xlsx --mapping rag/examples/source_v2_mapping.json \
  --db-profile supabase --collection-id "$RAG_COLLECTION_ID" \
  --tokenizer-path "$RAG_TOKENIZER_PATH" > source_v2_index_result.json

# 3. 결과 JSON을 검토한 뒤 모든 Source Unit을 명시적으로 게시한다.
uv run --project rag --locked starter-rag publish \
  --from-index-result source_v2_index_result.json \
  --db-profile supabase --collection-id "$RAG_COLLECTION_ID"

# 4. 게시된 근거만 검색 (Backend 역시 SearchPort만 사용)
uv run --project rag --locked starter-rag search '절차 안내' \
  --db-profile supabase --collection-id "$RAG_COLLECTION_ID" --top-k 3
```

Source_v2는 31개 Unit을 별도 문서 버전으로 색인한다. 색인은 게시가 아니므로
게시되지 않은 자료는 검색에 노출되지 않는다. 출처 URL이 없을 때는 `None`을
유지하고, 화면 URL 비표시 자료의 내부 URL을 Evidence에 노출하지 않는다.
`RAG_COLLECTION_ID`는 로컬 실험값을 운영 기본값으로 사용하지 말고 승인된 값을
명시해야 한다. 운영 접속 결과·적재 행 수·Golden Truth 재평가는 별도 기록한다.
