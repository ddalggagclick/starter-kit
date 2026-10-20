# Python 테스트 실행 규칙

- Python 테스트는 저장소 루트에서 `uv run`으로 실행한다. 전체 unittest 명령은 `uv run python -m unittest discover -s tests -v`다.
- bare `python` 또는 `python3`로 실행한 결과만으로 의존성이 없다고 판단하지 않는다. 셸이 프로젝트 `.venv`가 아닌 시스템 Python을 선택할 수 있다.
- import 오류를 보고하기 전에 `uv run python -c 'import sys; print(sys.executable); print(sys.version)'`으로 인터프리터를 확인하고, 필요한 패키지도 같은 `uv run` 환경에서 import 확인한다.
- 재발 방지 사례: 시스템 Python 3.14.7에는 FastAPI가 없어 전체 unittest에서 import 오류가 났지만, 저장소 uv 환경의 Python 3.13.15에는 FastAPI 0.143.3이 있었고 전체 74개 테스트가 통과했다.
