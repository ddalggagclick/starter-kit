/*
 * 담당: [A] | 책임: 체크리스트와 대화 저장 동의 상태 관리.
 * PRD: E4 / 스토리 4-1, 4-3 / 태스크 4-1-2, 4-3-2, 4-3-3, 4-3-4. 화면정의서 D-03·D-04·D-10. 개인정보 정책 S04-A·S07-C.
 * 구현: namespace·항목별 동의 기록, 동의 확인 후 저장, 데이터 삭제(동의 유지)와 동의 철회(데이터+동의 해제) 분리.
 * 완료 기준: 한 항목 동의가 다른 항목 저장을 허용하지 않고, 삭제 실패 시 동의를 해제하거나 완료로 반환하지 않는다.
 * 제한사항: 동의는 체크리스트·AI 대화 2개로 따로 받는다(D-03, PRD 4-1). 개인정보 정책 S03-A의 단일 동의 표현과 다르며
 *   팀 회의 결과에 따라 바뀔 수 있다. 동의 UI(4-1-1, 4-1-3)와 서버 저장 동의(4-5, 4-6)는 후속 이슈다.
 */
import type { StorageConsentScope, StorageStatus } from "@/shared/contracts/ui"
import { attemptStorage, type InheritanceDb, type StorageNamespace, type StorageResult } from "./db"

export const CONSENT_SCOPES: readonly StorageConsentScope[] = ["checklist", "chat"]

// 동의 항목마다 그 항목 데이터가 든 테이블만 고른다. 한 항목의 처리가 다른 항목 테이블에 닿지 않게 한다(D-04).
const scopeTables = (db: InheritanceDb, scope: StorageConsentScope) =>
  scope === "checklist" ? [db.checklists] : [db.conversations, db.messages]

const clearScopeData = async (
  db: InheritanceDb,
  namespace: StorageNamespace,
  scope: StorageConsentScope,
) => {
  if (scope === "checklist") {
    await db.checklists.delete(namespace)
    return
  }
  await db.messages.where("namespace").equals(namespace).delete()
  await db.conversations.where("namespace").equals(namespace).delete()
}

// 읽기에 실패하면 두 항목 모두 "failed"다. 화면은 이를 저장 불가로 보여주고 미동의처럼 동작한다(D-10).
export const loadConsentStatuses = async (
  db: InheritanceDb,
  namespace: StorageNamespace,
): Promise<Record<StorageConsentScope, StorageStatus>> => {
  const result = await attemptStorage(() =>
    db.consents.where("namespace").equals(namespace).toArray(),
  )
  if (!result.ok) return { checklist: "failed", chat: "failed" }
  const granted = new Set(result.value.map((record) => record.scope))
  return {
    checklist: granted.has("checklist") ? "ready" : "not-consented",
    chat: granted.has("chat") ? "ready" : "not-consented",
  }
}

// 사용자가 동의 문구를 확인하고 [저장]을 누른 뒤에만 호출한다(P01-C). 다른 항목 동의는 바꾸지 않는다.
export const grantConsent = (
  db: InheritanceDb,
  namespace: StorageNamespace,
  scope: StorageConsentScope,
): Promise<StorageResult<void>> =>
  attemptStorage(async () => {
    await db.consents.put({ namespace, scope, grantedAt: Date.now() })
  })

// 동의 확인과 저장을 한 트랜잭션에서 처리해, 확인 직후 철회가 끼어들어 동의 없는 데이터가 남지 않게 한다.
// write에는 db.ts의 저장 함수를 넘긴다. 그 함수의 테이블은 scope 테이블 안에 있어야 한다.
export const writeWithConsent = (
  db: InheritanceDb,
  namespace: StorageNamespace,
  scope: StorageConsentScope,
  write: () => Promise<StorageResult<void>>,
): Promise<StorageResult<void>> =>
  attemptStorage(() =>
    db.transaction(
      "rw",
      [db.consents, ...scopeTables(db, scope)],
      async (): Promise<StorageResult<void>> => {
        if (!(await db.consents.get([namespace, scope]))) {
          return { ok: false, reason: "not-consented" }
        }
        return write()
      },
    ),
  ).then((result) => (result.ok ? result.value : result))

// [체크리스트 삭제]·[대화 기록 삭제]: 데이터만 지우고 동의는 유지한다(4-3-2).
export const deleteScopeData = (
  db: InheritanceDb,
  namespace: StorageNamespace,
  scope: StorageConsentScope,
): Promise<StorageResult<void>> =>
  attemptStorage(() =>
    db.transaction("rw", scopeTables(db, scope), () => clearScopeData(db, namespace, scope)),
  )

// 동의 철회: 데이터를 먼저 지우고 같은 트랜잭션에서 동의를 해제한다(4-3-3).
// 중간에 실패하면 전체가 취소되어 데이터와 동의가 모두 남고, 실패를 그대로 돌려준다(4-3-4).
// 메모리(Zustand) 상태 초기화(T07-A)는 이 결과가 성공일 때 화면 쪽에서 한다.
export const revokeConsent = (
  db: InheritanceDb,
  namespace: StorageNamespace,
  scope: StorageConsentScope,
): Promise<StorageResult<void>> =>
  attemptStorage(() =>
    db.transaction("rw", [db.consents, ...scopeTables(db, scope)], async () => {
      await clearScopeData(db, namespace, scope)
      await db.consents.delete([namespace, scope])
    }),
  )
