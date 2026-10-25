/*
 * 담당: [A] | 책임: 동의된 체크리스트·대화 기록의 Dexie 저장.
 * PRD: E4 / 스토리 4-2 / 태스크 4-2-1, 4-2-2, 4-2-4. 화면정의서 D-03·D-04·D-10·D-16. 개인정보 정책 S10-A·P02-B.
 * 구현: IndexedDB 스키마, Guest/계정 namespace별 읽기·쓰기·삭제, 저장 실패를 "저장 불가" 결과로 변환.
 * 완료 기준: 다른 namespace 기록은 조회·삭제되지 않고, 저장 실패를 성공으로 반환하지 않는다.
 * 제한사항: 이 모듈의 저장 함수는 동의 여부를 검사하지 않는다. 화면 코드는 consent.ts의 writeWithConsent로 감싸 호출한다.
 *   화면·Zustand 연결(2-5-3, 3-6-1)과 계정 ID 연결(5-3)은 후속 이슈다.
 *   JSON 백업·복원과 충돌 UI(4-4-1~4-4-3)는 MVP+4일 이후다.
 */
import Dexie, { type DexieOptions, type Table } from "dexie"
import type { InitialAnswers, ProcedureId, RiskAnswer, RiskId } from "@/shared/contracts/domain"
import type { StorageConsentScope } from "@/shared/contracts/ui"
import type { ProcedureState } from "@/shared/state/inheritance-store"

// 계정 ID에 접두어를 붙여 Guest 기록과 이름이 겹치지 않게 한다.
export type StorageNamespace = "guest" | `account:${string}`
export const GUEST_NAMESPACE: StorageNamespace = "guest"

export const accountNamespace = (accountId: string): StorageNamespace => {
  const trimmed = accountId.trim()
  // 빈 ID로 만든 namespace는 모든 계정이 공유하게 되므로 거부한다.
  if (!trimmed) throw new Error("accountId가 비어 있어 namespace를 만들 수 없습니다.")
  return `account:${trimmed}`
}

// 체크리스트 동의(D-03 ①) 대상. namespace당 현재 상태 1건만 둔다.
export type ChecklistRecord = {
  namespace: StorageNamespace
  answers: InitialAnswers | null
  riskAnswers: Partial<Record<RiskId, RiskAnswer>>
  procedureStates: Record<ProcedureId, ProcedureState>
  updatedAt: number
}

export type ChecklistSnapshot = Omit<ChecklistRecord, "namespace" | "updatedAt">

// AI 대화 동의(D-03 ②) 대상. 체크리스트와 다른 테이블이라 한쪽 삭제가 다른 쪽에 닿지 않는다(D-04).
export type ConversationRecord = {
  id: string
  namespace: StorageNamespace
  // 첫 질문 앞부분(D-14). 잘라내는 길이는 화면 쪽에서 정한다.
  title: string
  createdAt: number
  updatedAt: number
}

// 이 모듈은 출처를 검증하지 않고 받은 그대로 저장한다.
// 호출하는 쪽에서 서버가 검증해 보낸 출처(SseResultEvent.sources)만 넘겨야 한다. URL을 만들거나 고치지 않는다.
export type StoredSource = { title: string; url: string }

export type MessageRecord = {
  id: string
  conversationId: string
  namespace: StorageNamespace
  role: "user" | "assistant"
  content: string
  sources: StoredSource[]
  createdAt: number
}

// 레코드가 있으면 동의한 상태다. 철회하면 레코드를 지우므로 "동의 안 함"을 따로 저장하지 않는다.
export type ConsentRecord = {
  namespace: StorageNamespace
  scope: StorageConsentScope
  grantedAt: number
}

export type StorageFailureReason =
  | "unavailable"
  | "quota-exceeded"
  | "not-found"
  | "not-consented"
  | "unknown"

export type StorageResult<T> = { ok: true; value: T } | { ok: false; reason: StorageFailureReason }

export const INHERITANCE_DB_NAME = "inheritance-guide"

// 대화·메시지 기본 키에 namespace를 넣어, 다른 계정이 같은 ID를 써도 서로 다른 레코드가 되게 한다.
type NamespacedKey = [StorageNamespace, string]

export class InheritanceDb extends Dexie {
  checklists!: Table<ChecklistRecord, StorageNamespace>
  conversations!: Table<ConversationRecord, NamespacedKey>
  messages!: Table<MessageRecord, NamespacedKey>
  consents!: Table<ConsentRecord, [StorageNamespace, StorageConsentScope]>

  // options는 테스트에서 fake-indexeddb를 주입할 때만 쓴다.
  constructor(name: string = INHERITANCE_DB_NAME, options?: DexieOptions) {
    super(name, options)
    // 스키마를 바꾸면 기존 사용자 기록 보존을 위해 version(2)를 추가하고 upgrade를 작성한다.
    this.version(1).stores({
      checklists: "namespace",
      conversations: "[namespace+id], namespace, [namespace+updatedAt]",
      messages: "[namespace+id], namespace, [namespace+conversationId]",
      consents: "[namespace+scope]",
    })
  }
}

// Dexie를 브라우저 전역 IndexedDB에 연결한다. 실제 열기는 첫 읽기·쓰기 때 일어난다.
export const inheritanceDb = new InheritanceDb()

const UNAVAILABLE_ERRORS = new Set([
  "MissingAPIError",
  "OpenFailedError",
  "DatabaseClosedError",
  "InvalidStateError",
  "SecurityError",
  "VersionError",
])

const errorName = (error: unknown): string | undefined =>
  error instanceof Error || error instanceof DOMException ? error.name : undefined

// Dexie는 원래 오류를 inner에 감싸 보내므로 바깥과 안쪽 이름을 모두 본다.
const toFailureReason = (error: unknown): StorageFailureReason => {
  const names = [errorName(error), errorName((error as { inner?: unknown } | null)?.inner)]
  if (names.some((name) => name?.includes("QuotaExceeded"))) return "quota-exceeded"
  if (names.some((name) => name !== undefined && UNAVAILABLE_ERRORS.has(name))) return "unavailable"
  return "unknown"
}

// 사생활 보호 모드·용량 초과 등에서도 화면이 멈추지 않도록 예외를 결과로 바꾼다(S10-A, 4-2-4).
// 오류 메시지에 기록 원문이 섞일 수 있어 로그를 남기지 않는다.
export const attemptStorage = async <T>(operation: () => Promise<T>): Promise<StorageResult<T>> => {
  try {
    return { ok: true, value: await operation() }
  } catch (error) {
    return { ok: false, reason: toFailureReason(error) }
  }
}

// 이 namespace에 대상 대화가 없으면 false를 돌려받아 "not-found"로 알린다.
const attemptOwned = async (operation: () => Promise<boolean>): Promise<StorageResult<void>> => {
  const result = await attemptStorage(operation)
  if (!result.ok) return result
  return result.value ? { ok: true, value: undefined } : { ok: false, reason: "not-found" }
}

export const saveChecklist = (
  db: InheritanceDb,
  namespace: StorageNamespace,
  snapshot: ChecklistSnapshot,
): Promise<StorageResult<void>> =>
  attemptStorage(async () => {
    await db.checklists.put({ ...snapshot, namespace, updatedAt: Date.now() })
  })

// 기록이 없으면 value가 null이다. 실패(ok: false)와 구분해 "저장 불가"를 잘못 보여주지 않는다.
export const loadChecklist = (
  db: InheritanceDb,
  namespace: StorageNamespace,
): Promise<StorageResult<ChecklistSnapshot | null>> =>
  attemptStorage(async () => {
    const record = await db.checklists.get(namespace)
    if (!record) return null
    const { answers, riskAnswers, procedureStates } = record
    return { answers, riskAnswers, procedureStates }
  })

export const deleteChecklist = (
  db: InheritanceDb,
  namespace: StorageNamespace,
): Promise<StorageResult<void>> =>
  attemptStorage(async () => {
    await db.checklists.delete(namespace)
  })

export const saveConversation = (
  db: InheritanceDb,
  conversation: ConversationRecord,
): Promise<StorageResult<void>> =>
  // 키가 [namespace+id]라 조회 없이 저장해도 다른 계정 대화에 닿지 않는다. 동시 저장에도 서로 덮어쓰지 않는다.
  attemptStorage(async () => {
    await db.conversations.put(conversation)
  })

// 대화 존재 확인, 메시지 저장, 대화 updatedAt 갱신을 한 트랜잭션으로 묶는다.
// 확인과 저장 사이에 대화가 지워져 주인 없는 메시지가 남는 일을 막는다.
export const addMessage = (
  db: InheritanceDb,
  message: MessageRecord,
): Promise<StorageResult<void>> =>
  attemptOwned(() =>
    db.transaction("rw", db.conversations, db.messages, async () => {
      const key: NamespacedKey = [message.namespace, message.conversationId]
      const conversation = await db.conversations.get(key)
      if (!conversation) return false
      await db.messages.put(message)
      // 오래된 메시지가 늦게 저장돼도 목록 순서(최신순)가 과거로 돌아가지 않게 한다.
      await db.conversations.update(key, {
        updatedAt: Math.max(conversation.updatedAt, message.createdAt),
      })
      return true
    }),
  )

// 최근에 이어 쓴 대화가 위에 오도록 정렬한다(S10 최신순).
export const listConversations = (
  db: InheritanceDb,
  namespace: StorageNamespace,
): Promise<StorageResult<ConversationRecord[]>> =>
  attemptStorage(() =>
    db.conversations
      .where("[namespace+updatedAt]")
      .between([namespace, Dexie.minKey], [namespace, Dexie.maxKey])
      .reverse()
      .toArray(),
  )

export const loadMessages = (
  db: InheritanceDb,
  namespace: StorageNamespace,
  conversationId: string,
): Promise<StorageResult<MessageRecord[]>> =>
  attemptStorage(() =>
    db.messages
      .where("[namespace+conversationId]")
      .equals([namespace, conversationId])
      .sortBy("createdAt"),
  )

export const deleteConversation = (
  db: InheritanceDb,
  namespace: StorageNamespace,
  conversationId: string,
): Promise<StorageResult<void>> =>
  attemptOwned(() =>
    db.transaction("rw", db.conversations, db.messages, async () => {
      const key: NamespacedKey = [namespace, conversationId]
      if (!(await db.conversations.get(key))) return false
      await db.messages
        .where("[namespace+conversationId]")
        .equals([namespace, conversationId])
        .delete()
      await db.conversations.delete(key)
      return true
    }),
  )

// [대화 기록 삭제]: 이 namespace의 대화만 지운다. 체크리스트와 다른 계정 기록은 그대로 둔다(D-04).
export const deleteAllConversations = (
  db: InheritanceDb,
  namespace: StorageNamespace,
): Promise<StorageResult<void>> =>
  attemptStorage(() =>
    db.transaction("rw", db.conversations, db.messages, async () => {
      await db.messages.where("namespace").equals(namespace).delete()
      await db.conversations.where("namespace").equals(namespace).delete()
    }),
  )
