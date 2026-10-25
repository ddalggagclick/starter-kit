/*
 * 담당: [A] | 책임: W-07 AI 대화 저장 동의 상태, 대화 저장·목록·열기·삭제(이 기기 IndexedDB).
 * PRD: E3·E4 / 태스크 4-1-1(W-07), 3-6-1, 3-6-2, 3-6-3. 화면정의서 D-01·D-03·D-05·D-10·D-14. 정책 S08-A·T11-B.
 * 구현: 체크리스트 동의와 따로 받는다. 동의 기록과 지금 화면의 대화를 한 트랜잭션으로 저장하고,
 *   이후 질문이 끝날 때마다 순서대로 저장한다. 표시 상태는 실제 저장 결과로만 정한다.
 *   저장 규칙: 검증된 답변(S3)은 본문·출처, 판단 유보(S7)는 질문만(답변 빈 값), 기술 오류(S6)·사용 제한(S9)은 저장하지 않는다.
 * 제한사항: 저장은 shared/storage의 동의 확인 함수로만 한다. 서버에 대화 원문을 보내 저장하지 않는다.
 *   [대화 기록 삭제] 전체 삭제·동의 철회 UI(4-3)는 후속 이슈다.
 */
import { useCallback, useEffect, useRef, useState } from "react"
import type { SseResultEvent } from "@/shared/api/types"
import type { StorageStatus } from "@/shared/contracts/ui"
import {
  type ChatWriteInput,
  grantChatConsentWithConversation,
  loadConsentStatuses,
  type NewMessage,
  saveChatWithConsent,
} from "@/shared/storage/consent"
import {
  type ConversationRecord,
  deleteConversation,
  type InheritanceDb,
  listConversations,
  loadMessages,
  type MessageRecord,
  type StorageNamespace,
} from "@/shared/storage/db"
import type { ChatOutcome } from "./use-chat-stream"

// retries: 이 질문에 [다시 시도]를 누른 횟수. restored: 저장 기록에서 다시 연 질문(타이핑 효과 없이 표시).
export type ChatTurn = {
  id: number
  question: string
  outcome: ChatOutcome
  retries: number
  restored?: boolean
}

export type ConversationMeta = { id: string; title: string; createdAt: number }

export type ChatStorageStatus = StorageStatus | "checking"

const TITLE_CODE_POINTS = 30

// 이전 대화 제목은 첫 질문 앞부분이다(D-14).
export const conversationTitle = (firstQuestion: string): string => {
  const characters = Array.from(firstQuestion.trim())
  return characters.length > TITLE_CODE_POINTS
    ? `${characters.slice(0, TITLE_CODE_POINTS).join("")}…`
    : characters.join("")
}

// 질문 하나를 저장할 메시지로 바꾼다. 기술 오류·사용 제한은 저장하지 않아 null.
export const turnToMessages = (
  conversationId: string,
  turn: ChatTurn,
  createdAt: number,
): NewMessage[] | null => {
  if (turn.outcome.kind === "error") return null
  const question: NewMessage = {
    id: `${turn.id}-q`,
    conversationId,
    role: "user",
    content: turn.question,
    sources: [],
    createdAt,
  }
  const result = turn.outcome.result
  const answer: NewMessage = {
    id: `${turn.id}-a`,
    conversationId,
    role: "assistant",
    // 판단 유보는 답변 본문이 없다. 빈 값으로 남겨 다시 열 때 판단 유보로 보인다.
    content: turn.outcome.kind === "answered" ? (result.answer ?? "") : "",
    sources:
      turn.outcome.kind === "answered"
        ? (result.sources ?? []).map((source) => ({
            title: source.title ?? "",
            url: source.url ?? null,
          }))
        : [],
    createdAt: createdAt + 1,
  }
  return [question, answer]
}

const restoredResult = (message: MessageRecord | undefined): ChatOutcome => {
  const answered = Boolean(message?.content) && (message?.sources.length ?? 0) > 0
  const result: SseResultEvent = answered
    ? {
        state: "answered",
        answer: message?.content ?? "",
        sources: message?.sources.map((source) => ({
          title: source.title,
          url: source.url ?? undefined,
        })),
        remainingToday: null,
        reasonCode: null,
      }
    : { state: "withheld", answer: null, sources: [], remainingToday: null, reasonCode: null }
  return answered ? { kind: "answered", result } : { kind: "withheld", result }
}

// 저장된 메시지(작성 순)를 화면의 질문 목록으로 되돌린다. 사용자 질문 뒤의 답변을 짝지어 읽는다.
export const messagesToTurns = (messages: MessageRecord[]): ChatTurn[] => {
  const turns: ChatTurn[] = []
  messages.forEach((message, index) => {
    if (message.role !== "user") return
    const next = messages[index + 1]
    const answer = next?.role === "assistant" ? next : undefined
    const numericId = Number(message.id.split("-")[0])
    turns.push({
      id: Number.isFinite(numericId) ? numericId : index,
      question: message.content,
      outcome: restoredResult(answer),
      retries: 0,
      restored: true,
    })
  })
  return turns
}

// 동의 전에 쌓인 지금 대화를 한 번에 저장할 입력. 저장할 질문이 없으면 null.
export const conversationWriteInput = (
  meta: ConversationMeta,
  turns: ChatTurn[],
): ChatWriteInput | null => {
  let clock = meta.createdAt
  const messages = turns.flatMap((turn) => {
    clock += 2
    return turnToMessages(meta.id, turn, clock) ?? []
  })
  if (messages.length === 0) return null
  return {
    conversation: { ...meta, updatedAt: clock + 1 },
    messages,
  }
}

// W-07에서 쓰는 AI 대화 저장 연결. namespace가 바뀌면 상태를 다시 읽는다.
export const useChatStorage = (db: InheritanceDb, namespace: StorageNamespace) => {
  const [status, setStatus] = useState<ChatStorageStatus>("checking")
  const [declined, setDeclined] = useState(false)
  const [conversations, setConversations] = useState<ConversationRecord[]>([])
  // 화면 표시와 별개로 "이 namespace에 동의가 확인됨". 저장은 이 값만 본다.
  const consented = useRef(false)
  // 이 namespace에 이미 저장된 대화 ID. 처음 저장할 때만 대화 정보를 함께 쓴다.
  const savedIds = useRef(new Set<string>())
  const queue = useRef<Promise<void>>(Promise.resolve())
  // namespace가 바뀐 뒤 도착한 이전 영역의 결과를 버린다.
  const generation = useRef(0)

  const refreshList = useCallback(
    async (gen: number) => {
      const listed = await listConversations(db, namespace)
      if (gen !== generation.current) return
      if (listed.ok) {
        setConversations(listed.value)
        savedIds.current = new Set(listed.value.map((record) => record.id))
      }
    },
    [db, namespace],
  )

  useEffect(() => {
    const gen = generation.current + 1
    generation.current = gen
    consented.current = false
    savedIds.current = new Set()
    setStatus("checking")
    setDeclined(false)
    setConversations([])
    void (async () => {
      const statuses = await loadConsentStatuses(db, namespace)
      if (gen !== generation.current) return
      if (statuses.chat !== "ready") {
        setStatus(statuses.chat)
        return
      }
      const listed = await listConversations(db, namespace)
      if (gen !== generation.current) return
      if (!listed.ok) {
        setStatus("failed")
        return
      }
      consented.current = true
      savedIds.current = new Set(listed.value.map((record) => record.id))
      setConversations(listed.value)
      setStatus("ready")
    })()
  }, [db, namespace])

  // 사용자가 정책을 확인하고 [저장]을 눌렀을 때(또는 S11 [이 기기에 저장하고 이동])만 호출한다(P01-C).
  // 성공 여부를 돌려준다.
  const grant = useCallback(
    async (meta: ConversationMeta | null, turns: ChatTurn[]): Promise<boolean> => {
      const gen = generation.current
      const input = meta ? conversationWriteInput(meta, turns) : null
      const result = await grantChatConsentWithConversation(db, namespace, input)
      if (gen !== generation.current) return false
      if (!result.ok) {
        setStatus("failed")
        return false
      }
      consented.current = true
      if (input?.conversation) savedIds.current.add(input.conversation.id)
      setStatus("ready")
      await refreshList(gen)
      return true
    },
    [db, namespace, refreshList],
  )

  // 질문 하나가 끝날 때 호출한다. 동의 전이면 아무것도 쓰지 않는다. 저장은 순서대로 한다.
  const saveTurn = useCallback(
    (meta: ConversationMeta, turn: ChatTurn): Promise<void> => {
      const gen = generation.current
      queue.current = queue.current.then(async () => {
        if (!consented.current || gen !== generation.current) return
        const messages = turnToMessages(meta.id, turn, Date.now())
        if (!messages) return
        const input: ChatWriteInput = savedIds.current.has(meta.id)
          ? { messages }
          : {
              conversation: { ...meta, updatedAt: meta.createdAt },
              messages,
            }
        const result = await saveChatWithConsent(db, namespace, input)
        if (gen !== generation.current) return
        if (!result.ok) {
          if (result.reason === "not-consented") consented.current = false
          setStatus(result.reason === "not-consented" ? "not-consented" : "failed")
          return
        }
        savedIds.current.add(meta.id)
        setStatus("ready")
        await refreshList(gen)
      })
      return queue.current
    },
    [db, namespace, refreshList],
  )

  // 저장된 대화를 다시 연다. 읽지 못하면 null.
  const open = useCallback(
    async (conversationId: string): Promise<ChatTurn[] | null> => {
      const loaded = await loadMessages(db, namespace, conversationId)
      return loaded.ok ? messagesToTurns(loaded.value) : null
    },
    [db, namespace],
  )

  // 대화 하나를 지운다(S08-A). 성공 여부를 돌려준다.
  const remove = useCallback(
    async (conversationId: string): Promise<boolean> => {
      const gen = generation.current
      const result = await deleteConversation(db, namespace, conversationId)
      if (gen !== generation.current) return false
      if (result.ok) savedIds.current.delete(conversationId)
      await refreshList(gen)
      return result.ok
    },
    [db, namespace, refreshList],
  )

  const isSaved = useCallback((conversationId: string) => savedIds.current.has(conversationId), [])

  return {
    status,
    declined,
    decline: () => setDeclined(true),
    conversations,
    grant,
    saveTurn,
    open,
    remove,
    isSaved,
    // 테스트·화면 이탈 전 대기용
    flush: () => queue.current,
  }
}

export type ChatStorage = ReturnType<typeof useChatStorage>

// 화면 표시용 날짜(월/일)
export const conversationDate = (timestamp: number): string => {
  const date = new Date(timestamp)
  return `${date.getMonth() + 1}/${date.getDate()}`
}
