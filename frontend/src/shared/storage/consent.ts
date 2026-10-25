/*
 * 담당: [A] | 책임: 체크리스트와 대화 저장 동의 상태 관리, 동의를 확인한 로컬 저장.
 * PRD: E4 / 스토리 4-1, 4-3 / 태스크 4-1-2, 4-3-2, 4-3-3, 4-3-4. 화면정의서 D-03·D-04·D-10. 개인정보 정책 S04-A·S07-C.
 * 구현: namespace·항목별 동의 기록, 동의 확인 후 저장, 데이터 삭제(동의 유지)와 동의 철회(데이터+동의 해제) 분리.
 * 완료 기준: 한 항목·한 계정의 동의가 다른 항목·계정 저장을 허용하지 않고, 실패하면 트랜잭션 전체를 되돌린다.
 * 상태: 로컬(IndexedDB) 저장 유틸리티만 구현했다. 위 네 태스크는 미완료다.
 *   남은 일: 정책 확인+명시 체크 화면에서 호출(4-1-2), 삭제·철회 UI(4-3-2·4-3-3),
 *   저장소별 잔존 상태 표시·재시도와 서버 삭제 실패 독립 보고(4-3-4).
 * 제한사항: 동의는 체크리스트·AI 대화 2개로 따로 받는다(D-03, PRD 4-1). 개인정보 정책 S03-A의 단일 동의 표현과 다르며
 *   팀 회의 결과에 따라 바뀔 수 있다. 서버 저장 동의(4-5, 4-6)는 백엔드 API 확정 후 다룬다.
 */
import type { StorageConsentScope, StorageStatus } from "@/shared/contracts/ui"
import {
  attemptStorage,
  type ChecklistSnapshot,
  type ConversationRecord,
  type InheritanceDb,
  type MessageRecord,
  StorageAbortError,
  type StorageNamespace,
  type StorageResult,
} from "./db"

export const CONSENT_SCOPES: readonly StorageConsentScope[] = ["checklist", "chat"]

// 입력에서 namespace를 빼고 동의를 확인한 namespace를 이 모듈이 직접 넣는다.
// 호출자가 동의한 계정과 다른 계정으로 쓰는 경로를 타입과 실행 양쪽에서 막는다.
export type NewConversation = Omit<ConversationRecord, "namespace">
export type NewMessage = Omit<MessageRecord, "namespace">

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

// 동의 확인과 쓰기를 한 트랜잭션에서 처리해, 확인 직후 철회가 끼어들어 동의 없는 데이터가 남지 않게 한다.
// body 안의 모든 실패는 예외로 던져야 한다. 그래야 앞선 쓰기까지 함께 되돌린다.
const writeInConsentedScope = (
  db: InheritanceDb,
  namespace: StorageNamespace,
  scope: StorageConsentScope,
  body: () => Promise<void>,
): Promise<StorageResult<void>> =>
  attemptStorage(() =>
    db.transaction("rw", [db.consents, ...scopeTables(db, scope)], async () => {
      if (!(await db.consents.get([namespace, scope]))) {
        throw new StorageAbortError("not-consented")
      }
      await body()
    }),
  )

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

// namespace당 현재 체크리스트 1건을 덮어쓴다. 체크리스트 동의가 없으면 not-consented.
export const saveChecklistWithConsent = (
  db: InheritanceDb,
  namespace: StorageNamespace,
  snapshot: ChecklistSnapshot,
): Promise<StorageResult<void>> =>
  writeInConsentedScope(db, namespace, "checklist", async () => {
    const { answers, riskAnswers, procedureStates } = snapshot
    await db.checklists.put({
      answers,
      riskAnswers,
      procedureStates,
      namespace,
      updatedAt: Date.now(),
    })
  })

// 대화 생성과 메시지 추가를 한 번에 처리한다. 대화 동의가 없으면 not-consented.
// 메시지의 대화가 이 namespace에 없으면 not-found이며, 같은 호출에서 먼저 저장한 대화·메시지도 되돌린다.
// sources는 서버가 검증해 보낸 값(SseResultEvent.sources)만 넘긴다. 이 함수는 출처를 검증하지 않는다.
export const saveChatWithConsent = (
  db: InheritanceDb,
  namespace: StorageNamespace,
  input: { conversation?: NewConversation; messages?: NewMessage[] },
): Promise<StorageResult<void>> =>
  writeInConsentedScope(db, namespace, "chat", async () => {
    // 입력에 namespace가 섞여 들어와도 동의를 확인한 값으로 덮어쓰도록 마지막에 둔다.
    if (input.conversation) await db.conversations.put({ ...input.conversation, namespace })
    for (const message of input.messages ?? []) {
      const key: [StorageNamespace, string] = [namespace, message.conversationId]
      const conversation = await db.conversations.get(key)
      if (!conversation) throw new StorageAbortError("not-found")
      await db.messages.put({ ...message, namespace })
      // 오래된 메시지가 늦게 저장돼도 목록 순서(최신순)가 과거로 돌아가지 않게 한다.
      await db.conversations.update(key, {
        updatedAt: Math.max(conversation.updatedAt, message.createdAt),
      })
    }
  })

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
