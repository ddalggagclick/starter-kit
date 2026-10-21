<!-- 책임: [D] Docling Parser의 설치 형식과 형식별 추가 요구사항을 안내한다.
구현할 기능: 표준 설치와 선택 의존성·외부 런타임의 차이를 기록한다.
완료 기준: 형식 사용 전 추가 설치 또는 입력 조건을 확인할 수 있다. -->
# RAG Parser 형식과 의존성

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
