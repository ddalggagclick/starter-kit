<!-- 책임: [통합] Git 운영 브랜치 이력 복구 트러블슈팅 기록.
구현할 기능: Squash merge로 분리된 장기 브랜치 이력을 복구한 실제 PR/검증 근거와 재발 방지책을 문서화한다.
완료 기준: 원인, 작업 순서, 코드/이력 검증, 배포 검사, 잔여 위험을 구분한다. -->

# 트러블슈팅: dev → main Squash merge 후 이력 충돌 복구

- **기록일:** 2026-10-29 (KST)
- **저장소:** [ddalggagclick/starter-kit](https://github.com/ddalggagclick/starter-kit)
- **브랜치 정책:** `dev` = default/개발, `main` = 운영/배포
- **결과:** Git 이력 연결 복구 완료. 실제 다음 기능 PR 및 서비스 동작 E2E 테스트는 별도 검증 필요.

## 증상과 원인

`dev → main`을 Squash merge([#217](https://github.com/ddalggagclick/starter-kit/pull/217))하자, `main`에 개별 `dev` 커밋들의 부모 관계를 보존하지 않는 새로운 Squash 커밋이 만들어졌다. 이후 `dev`의 개발 커밋들이 계속 진행되면서 `dev → main` PR에 이미 배포된 변경이 포함되고 충돌이 발생했다. GitHub의 역방향 `main → dev` PR 추천은 이력 차이를 보여주는 UI이며 자동으로 따라야 하는 작업은 아니다.

과거 Squash 커밋 자체를 일반 Merge commit으로 소급 변경하지 않았다. `reset --hard`, 강제 push, 기존 `dev` 커밋 삭제 없이 새로운 복구 이력을 추가했다.

## 수행한 복구 절차 (실제 병합된 PR)

1. 원래 운영 `main`에서 시작한 임시 `repair/merge-history` 브랜치에, 기존 Squash PR #217을 되돌리는 [#228](https://github.com/ddalggagclick/starter-kit/pull/228)을 병합했다. **운영 `main`에 Revert를 직접 적용하지 않았다.**
2. 최신 `dev`를 복구 브랜치에 **Merge commit**으로 병합: [#229](https://github.com/ddalggagclick/starter-kit/pull/229), merge SHA `f1792d1fb48f4181e9683114e7c6fc601f01bec8`.
3. 복구 브랜치를 운영 `main`에 **Merge commit**으로 병합: [#230](https://github.com/ddalggagclick/starter-kit/pull/230), merge SHA `bf6ebceef50d65b880808c392d1349cc96e4b449`. 이 단계는 운영 배포를 트리거할 수 있으므로 일반적으로 PR의 변경 파일/검사 확인 후 수행한다.
4. 임시 브랜치는 이후 삭제되어도 된다. 복구 이력은 `main`의 병합 커밋에서 유지된다.

## 검증 증거 (2026-10-29 조회)

| 항목 | 관찰 결과 |
| --- | --- |
| #228, #229, #230 | 세 PR 모두 `merged: true` |
| `dev` HEAD | `525b35baab6ea1cc944d5551f2a7f00d1519c9f2` |
| `main` HEAD | `bf6ebceef50d65b880808c392d1349cc96e4b449` |
| `main` Merge commit의 부모 | 이전 운영 `919699094105d081c03ca386979cbca7df43e546` + 복구 결과 `f1792d1fb48f4181e9683114e7c6fc601f01bec8` |
| 복구 중 Merge commit #229의 부모 | Revert 결과 `44033d8416f543bbf50b9bc59ad1408a523bac0b` + `dev` HEAD |
| Git tree SHA (`dev`, #229, #230) | 모두 `3f64fcafc6f20cba332fc8d6e1d09287ec631fcc` — 파일 스냅샷 동일 |
| `main...dev` 비교 | `dev`는 `main`보다 5커밋 뒤, 앞선 커밋 0개, 변경 파일 0개 |
| 저장소 설정 | `default_branch: dev`, `allow_merge_commit: true` |
| `main` 커밋 배포 상태 검사 | Vercel – starter-kit / gil-web / gil-web-api 각각 `success` |

**판정:** 기존 Squash 때문에 끊긴 병합 계보가 연결되었고 현재 두 브랜치의 파일 트리는 같다. 이는 코드 스냅샷과 커밋 계보 검증이지 서비스 기능 E2E 또는 추후 기능 PR에 대한 충돌 없음 보장은 아니다. Vercel 상태 검사는 성공했지만 실제 서비스의 모든 동작은 별도 확인해야 한다.

## 재발 방지

- 장기 유지되는 `dev → main` 릴리스 PR은 **Create a merge commit**을 사용한다. 기능 브랜치 → `dev` 정책은 팀에서 별도로 정할 수 있다.
- `main`에 핫픽스를 직접 넣었다면 배포 후 변경을 `dev`에 다시 반영한다.
- PR 병합 전 `Files changed`, 충돌 여부, 필수 CI 및 배포 영향을 확인한다.
- 같은 이슈 재발 시 과거 Squash를 수정하거나 강제 push하지 말고 공통 조상/머지 부모 관계 및 두 브랜치의 트리 차이를 먼저 확인한다.
- `main → dev` 추천 UI 자체를 없애는 기능과 실제 Git 이력 충돌 해결은 별개의 문제다.

## 검증 범위

- **검증 완료:** PR 병합 상태, 두 브랜치 계보 및 tree SHA, 파일 차이, Merge commit 허용 여부, `main` 커밋에 연결된 3개 Vercel 상태 검사.
- **실행하지 않음:** 로컬 단위·통합·E2E 테스트, 신규 `dev → main` PR의 미래 머지 시험, 운영 서비스 수동 점검.
- **변경 파일:** 이 문서만 추가. 제품 코드·계약·CI·브랜치 보호 규칙은 수정하지 않음.

## 관련 자료

- [첫 운영 Squash PR #217](https://github.com/ddalggagclick/starter-kit/pull/217)
- [임시 브랜치 Revert PR #228](https://github.com/ddalggagclick/starter-kit/pull/228)
- [dev 이력 병합 PR #229](https://github.com/ddalggagclick/starter-kit/pull/229)
- [운영 main 복구 PR #230](https://github.com/ddalggagclick/starter-kit/pull/230)
