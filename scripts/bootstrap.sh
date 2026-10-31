#!/usr/bin/env bash
# 담당: [통합] | 책임: 선택 프로필에 필요한 로컬 개발 환경을 준비한다.
# 구현할 기능: 상속길잡이 전체, LLM CLI, RAG CLI 프로필별 잠금 설치와 개인 설정 준비.
# 코드 경계: 명령 출력에 비밀값·개인 경로를 노출하지 않고 DB/API를 변경하지 않는다.
# 완료 기준: lockfile 기반 설치, 숨김 설정 입력, 값 없는 doctor 상태 확인을 수행한다.
set +x
set -euo pipefail

if [[ ! -t 0 || ! -t 2 ]]; then
  printf '%s\n' 'bootstrap은 메뉴와 숨김 설정 입력을 위해 실제 터미널에서 실행해야 합니다.' >&2
  exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || {
  printf '%s\n' '저장소 위치를 확인할 수 없습니다.' >&2
  exit 2
}
repo_root=$(cd -- "$script_dir/.." && pwd) || {
  printf '%s\n' '저장소 위치를 확인할 수 없습니다.' >&2
  exit 2
}
cd "$repo_root" || {
  printf '%s\n' '저장소로 이동할 수 없습니다.' >&2
  exit 2
}

printf '%s\n' \
  '처음 실행할 환경을 선택하세요.' \
  '1) 상속길잡이 전체 (Backend + Frontend + LLM + RAG)' \
  '2) LLM CLI만' \
  '3) RAG CLI만'
read -r -p '선택 [1-3]: ' profile_choice

case "$profile_choice" in
  1) profile=inheritance ;;
  2) profile=llm ;;
  3) profile=rag ;;
  *)
    printf '%s\n' '1, 2, 3 중 하나를 선택하세요.' >&2
    exit 2
    ;;
esac

ollama_failover=false
if [[ "$profile" == llm ]]; then
  read -r -p 'LLM failover에 로컬 Ollama를 포함할까요? [y/N]: ' ollama_answer
  case "$ollama_answer" in
    [yY]|[yY][eE][sS]) ollama_failover=true ;;
    *) ollama_failover=false ;;
  esac
fi

if ! command -v python3.13 >/dev/null 2>&1; then
  printf '%s\n' \
    'Python 3.13을 설치하고 PATH에 추가한 뒤 다시 실행하세요.' \
    '공식 설치 안내: https://www.python.org/downloads/' >&2
  exit 1
fi

if ! python3.13 scripts/doctor.py preflight --profile "$profile"; then
  printf '%s\n' '사전 조건을 해결한 뒤 다시 실행하세요. 개인 설정은 입력하지 않았습니다.' >&2
  exit 1
fi

run_quietly() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '%s: OK\n' "$label"
  else
    local exit_status=$?
    printf '%s 실패 (종료 코드 %s). 패키지 관리자 상세 출력은 숨겼습니다.\n' \
      "$label" "$exit_status" >&2
    printf '%s' '상세 오류를 직접 확인할 명령:' >&2
    printf ' %q' "$@" >&2
    printf '\n' >&2
    return "$exit_status"
  fi
}

printf '%s\n' '선택한 프로필의 잠금 의존성을 설치합니다.'
case "$profile" in
  inheritance)
    run_quietly 'Python dependencies' uv sync --locked --group bootstrap
    run_quietly 'Frontend dependencies' npm ci --prefix frontend
    ;;
  llm)
    if [[ "$ollama_failover" == true ]]; then
      run_quietly 'Python dependencies' uv sync --package starter-llm --extra ollama --locked --group bootstrap
    else
      run_quietly 'Python dependencies' uv sync --package starter-llm --locked --group bootstrap
    fi
    ;;
  rag)
    run_quietly 'Python dependencies' uv sync --package starter-rag --extra ingestion --locked --group bootstrap
    ;;
esac

configure_args=(configure --profile "$profile")
if [[ "$profile" == llm ]]; then
  if [[ "$ollama_failover" == true ]]; then
    configure_args+=(--ollama-failover)
  else
    configure_args+=(--no-ollama-failover)
  fi
fi
configure_args+=(--doctor-check)
.venv/bin/python scripts/local_env.py "${configure_args[@]}"

printf '%s\n' '선택 프로필의 패키지 설치가 완료됐습니다.'
printf '%s\n' 'doctor의 RUNTIME PREREQUISITE: MISSING 항목은 해당 기능 실행 전에 준비해야 합니다.'
printf '%s\n' '설정 입력을 다시 열려면 bash scripts/bootstrap.sh를 실행하세요.'
case "$profile" in
  inheritance)
    printf '%s\n' 'Backend: .venv/bin/python scripts/local_env.py run uv run uvicorn app_entry:app --app-dir backend --port 8000'
    printf '%s\n' 'Frontend: npm --prefix frontend run dev'
    ;;
  llm)
    if [[ "$ollama_failover" == true ]]; then
      printf '%s\n' 'LLM: .venv/bin/python scripts/local_env.py run uv run --project llm --extra ollama --locked starter-llm status'
    else
      printf '%s\n' 'LLM: .venv/bin/python scripts/local_env.py run uv run --project llm --locked starter-llm status'
    fi
    ;;
  rag)
    printf '%s\n' 'RAG: .venv/bin/python scripts/local_env.py run uv run --project rag --extra ingestion --locked starter-rag status'
    ;;
esac
