#!/usr/bin/env bash
# 담당: [통합] | 책임: [통합] 향후 신규 환경 설치 스크립트 자리
# 구현할 기능: uv sync/npm ci 단계 명시; lockfile 생성 전 실행하지 않음
# 코드 경계: 검사·설치 보조만 한다. 시크릿/사용자 데이터가 로그에 출력되지 않게 한다.
# 완료 기준: 동일 내용을 다른 파일에 중복 구현하지 않고 검토/정적 검사 통과.
# 상태: Contract-first — 구현은 소유 담당자 PR에서 진행
set -euo pipefail
echo 'Contract-only scaffold: install/bootstrap intentionally not enabled.'
