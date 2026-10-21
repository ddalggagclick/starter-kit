<!--
담당: [A] | 책임: GitHub 이슈 #29의 저장소 내 사본. 작업 1개 = 이슈 1개 = 커밋 1개 기록 규칙에 따른다.
원본: https://github.com/ddalggagclick/starter-kit/issues/29
-->
# [chore] frontend 줄바꿈 LF 고정 (.gitattributes) #29

- **GitHub 이슈:** https://github.com/ddalggagclick/starter-kit/issues/29
- **브랜치:** `29-chore-frontend-lf-gitattributes` (dev에서 분기, push 안 함)
- **배경:** 이슈 #28 커밋 중 `LF will be replaced by CRLF` 경고가 나와 팀장 결정(해결 방법 (가))으로 Mock 2번 이슈 전에 처리한다.
- **변경 파일:** `frontend/.gitattributes`, 이 문서

## 목표

frontend 파일의 줄바꿈을 팀 기준(LF, `frontend/biome.jsonc`의 `lineEnding: lf`)으로 고정한다.
Git for Windows 기본값(`core.autocrlf=true`) 때문에 작업 파일이 CRLF로 꺼내져 Biome 포맷 검사와 어긋나는 문제를 막는다.
루트 `.gitattributes`는 통합 관리자 소유이므로 frontend 폴더에만 적용한다.

## 작업

- [x] `frontend/.gitattributes` 추가 (`* text=auto eol=lf`)
- [x] 저장소(index)의 frontend 파일 40개가 모두 LF인지 확인 → 기존 파일 내용 변경 없음
- [x] 이슈 문서 `frontend/docs/issues/` 작성

## 완료 조건

- 커밋에는 `frontend/.gitattributes`와 이슈 문서만 포함된다
- `git check-attr eol -- frontend/<파일>` 결과가 `eol: lf`
- 이미 CRLF로 꺼내진 작업 파일 38개의 LF 재적용은 별도 승낙 후 진행(내용 변경 없음)

## 확인 기록 (2026-10-21)

- `git ls-files --eol -- frontend`: index 40개 모두 `i/lf`, 작업 파일 38개 `w/crlf` · 2개 `w/lf`
- `core.autocrlf=true` 출처: `C:/Program Files/Git/etc/gitconfig` (Git for Windows 설치 기본값)
