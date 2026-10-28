/*
 * 담당: [A] | 책임: AI 대화의 동작(화면 모양 제외)을 한 곳에 모은 훅. 첫 화면 대화창(이슈 ③)이 이 훅으로 그린다.
 * 근거: #207. 첫 화면을 시안(https://claude.ai/artifact/T6VdodQVFJ3thyx4zpMyyN)대로 새로 디자인하기 위해
 *   AI 질문 화면(chat-page.tsx)의 동작만 떼어 냈다. 다른 이슈와 병렬로 작업하려고 새 파일만 만들었고,
 *   chat-page.tsx는 그대로 둔다(/ai는 기존 코드를 쓴다). /ai를 첫 화면으로 합친 뒤(이슈 ④) 중복을 정리한다.
 * PRD·규칙(chat-page.tsx와 같다): 200 코드 포인트, 직전 질문 3개, 같은 질문 [다시 시도] 3회(Q47), 422는 입력칸 오류,
 *   S6 기술 오류·S7 판단 유보·S9 사용 제한, 비로그인 남은 횟수(null이면 모름, 지어내지 않음), 새 대화 확인(S8·Q60),
 *   저장 동의한 경우만 저장(4-1-1), 실패한 첫 질문은 제목이 되지 않음(P2·D-14), 저장 안 된 대화 이탈 확인(S11·D-11).
 * 사용법: 로그인 계정(namespace)이 바뀌면 이 훅을 쓰는 컴포넌트를 key={namespace}로 새로 그린다(P1).
 *   전송 방식(Mock·실제 A08)은 쓰는 쪽이 transport로 넘긴다.
 * 제한사항: useBlocker를 쓰므로 데이터 라우터(createBrowserRouter 등) 안에서만 쓸 수 있다.
 */
import { useState } from "react"
import { useBlocker } from "react-router"
import { useAuthStore } from "@/features/auth/auth-store"
import { CHAT_INPUT_POLICY, countUnicodeCodePoints } from "@/shared/contracts/ui"
import { type InheritanceDb, inheritanceDb, type StorageNamespace } from "@/shared/storage/db"
// 규칙 함수·상한은 공용 부품 파일(chat-parts.tsx, #223)의 것을 쓴다(/ai 화면과 값이 어긋나지 않게).
import { inputErrorMessage, MAX_MANUAL_RETRIES, rateLimitKind } from "./chat-parts"
import {
  type ChatTurn,
  type ConversationMeta,
  conversationTitle,
  useChatStorage,
} from "./chat-storage"
import { useChatSessionStore } from "./chat-store"
import { type ChatTransport, useChatStream } from "./use-chat-stream"

const newConversationId = () =>
  globalThis.crypto?.randomUUID?.() ?? `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`

export function useChatSession({
  namespace,
  transport,
  db = inheritanceDb,
}: {
  namespace: StorageNamespace
  transport: ChatTransport
  db?: InheritanceDb
}) {
  const isGuest = useAuthStore((s) => s.accountId === null)
  const {
    externalNoticeAcknowledged,
    acknowledgeExternalNotice,
    guestRemaining,
    setGuestRemaining,
  } = useChatSessionStore()
  const [input, setInput] = useState("")
  const [turns, setTurns] = useState<ChatTurn[]>([])
  // 지금 대화. 첫 질문이 끝날 때 만든다(제목 = 첫 질문 앞부분, D-14).
  const [meta, setMeta] = useState<ConversationMeta | null>(null)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [inputError, setInputError] = useState<string | null>(null)
  const [cancelledNote, setCancelledNote] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [confirmingNewChat, setConfirmingNewChat] = useState(false)
  const storage = useChatStorage(db, namespace)
  const { ask, cancel, running, stage } = useChatStream(transport)

  // 남은 횟수가 0이 되면 다음 질문을 보내 429를 받기 전에 바로 안내하고 보내기를 막는다.
  // 남은 횟수를 모르면(null) 서버의 429 응답으로 안내한다.
  const guestLimitReached = isGuest && guestRemaining === 0
  const codePoints = countUnicodeCodePoints(input)
  const overLimit = codePoints > CHAT_INPUT_POLICY.maxQuestionCodePoints
  const saving = storage.status === "ready"
  const hasUnsent = input.trim() !== ""
  const hasConversation = turns.length > 0 || pendingQuestion !== null
  // [보내기]를 누를 수 있는지. 빈 입력은 누르면 "질문을 입력해 주세요."로 알린다(막지 않음).
  const canSend = !running && !overLimit && externalNoticeAcknowledged && !guestLimitReached

  async function send(question: string, earlierTurns: ChatTurn[], retries = 0) {
    setInputError(null)
    setCancelledNote(false)
    setPendingQuestion(question)
    // 같은 대화의 직전 사용자 질문 최대 3개만 보낸다.
    const previousQuestions = earlierTurns
      .map((turn) => turn.question)
      .slice(-CHAT_INPUT_POLICY.maxPreviousMessages)
    const outcome = await ask(question, previousQuestions)
    setPendingQuestion(null)
    // 취소했으면 결과가 없다.
    if (!outcome) return
    // 422는 대화에 남기지 않고 입력칸 아래 오류로 보여준다.
    if (outcome.kind === "error" && outcome.failure.status === 422) {
      setInputError(inputErrorMessage(outcome.failure))
      setInput(question)
      return
    }
    // 서버가 null을 보내면 남은 횟수를 모르는 것이다. 마지막 값을 지우고 숫자를 지어내지 않는다.
    if (outcome.kind !== "error" && isGuest) {
      setGuestRemaining(outcome.result.remainingToday ?? null)
    }
    // 비로그인 하루 한도일 때만 남은 횟수를 0으로 둔다(1분 제한은 횟수와 무관).
    if (
      outcome.kind === "error" &&
      outcome.failure.code === "RATE_LIMITED" &&
      isGuest &&
      rateLimitKind(outcome.failure, isGuest) === "guestDaily"
    ) {
      setGuestRemaining(0)
    }
    const turn: ChatTurn = { id: Date.now(), question, outcome, retries }
    setTurns((current) => [...current, turn])
    // 기술 오류·사용 제한은 저장하지 않으므로 대화 정보(제목)도 만들지 않는다(P2).
    if (outcome.kind === "error") return
    // 대화 정보와 제목은 처음 저장되는 질문(답변·판단 유보)으로 만든다(D-14).
    const conversation = meta ?? {
      id: newConversationId(),
      title: conversationTitle(question),
      createdAt: Date.now(),
    }
    if (!meta) setMeta(conversation)
    // 동의한 경우에만 저장된다(chat-storage가 확인).
    void storage.saveTurn(conversation, turn)
  }

  // [보내기]. 보낼 수 없으면 아무것도 하지 않고, 빈 질문이면 입력칸 오류를 보인다.
  function submit() {
    const question = input.trim()
    if (!question) {
      setInputError("질문을 입력해 주세요.")
      return
    }
    if (!canSend) return
    setInput("")
    void send(question, turns)
  }

  // 실패한 질문 다시 시도. 이전 실패는 대화에서 지우고 같은 질문을 다시 보낸다(대화에는 한 번만 남는다).
  function retry(turn: ChatTurn) {
    if (running || turn.retries >= MAX_MANUAL_RETRIES) return
    const remaining = turns.filter((item) => item.id !== turn.id)
    setTurns(remaining)
    void send(turn.question, remaining, turn.retries + 1)
  }

  // 진행 중인 질문 취소. 취소한 질문은 입력칸으로 돌려준다.
  function cancelQuestion() {
    cancel()
    if (pendingQuestion) setInput(pendingQuestion)
    setPendingQuestion(null)
    setCancelledNote(true)
  }

  function resetConversation() {
    cancel()
    setTurns([])
    setMeta(null)
    setInput("")
    setPendingQuestion(null)
    setCancelledNote(false)
    setInputError(null)
  }

  // S8: 저장 중이면 지금 대화는 이미 목록에 보관되어 확인 없이 새 대화를 연다. 미전송 입력이 있을 때만 묻는다.
  // 저장하지 않는 중이면 대화나 입력이 있을 때 묻는다(Q60).
  function requestNewChat() {
    const needsConfirm = hasUnsent || (!saving && hasConversation)
    if (needsConfirm) setConfirmingNewChat(true)
    else resetConversation()
  }
  function confirmNewChat() {
    setConfirmingNewChat(false)
    resetConversation()
  }
  const dismissNewChat = () => setConfirmingNewChat(false)

  // S11: 저장하지 않는(미동의·저장 불가) 대화나 입력이 있을 때, 사이트 안 다른 화면으로 이동하면 묻는다.
  // 새로고침·탭 닫기는 묻지 않는다(D-11). 공식 출처를 새 탭으로 여는 것은 이동이 아니다.
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      currentLocation.pathname !== nextLocation.pathname &&
      !saving &&
      (hasConversation || hasUnsent),
  )

  // [대화 기록 삭제]·동의 철회: 시작할 때 진행 중인 질문을 취소하고 보고 있던 대화를 비운다.
  // 지금 대화는 무효로 넘겨, 삭제 도중 끝난 답변이 지운 대화를 다시 만들지 않게 한다(chat-storage).
  const clearStorage = (action: (currentIds: string[]) => Promise<boolean>) => {
    const currentIds = meta ? [meta.id] : []
    resetConversation()
    return action(currentIds)
  }
  const deleteAllConversations = () => clearStorage(storage.removeAll)
  const revokeStorage = () => clearStorage(storage.revoke)

  // 정책 확인 후 [저장] 또는 S11 [이 기기에 저장하고 이동]: 동의와 지금 대화를 함께 저장한다.
  const grantStorage = () => storage.grant(meta, turns)

  async function openConversation(conversation: ConversationMeta) {
    setHistoryError(null)
    const restored = await storage.open(conversation.id)
    if (!restored) {
      setHistoryError("이전 대화를 불러오지 못했습니다. 다시 시도해 주세요.")
      return
    }
    cancel()
    setPendingQuestion(null)
    setCancelledNote(false)
    setMeta({ id: conversation.id, title: conversation.title, createdAt: conversation.createdAt })
    setTurns(restored)
  }

  async function removeConversation(conversationId: string) {
    setHistoryError(null)
    const ok = await storage.remove(conversationId)
    if (!ok) {
      setHistoryError("삭제하지 못했습니다. 다시 시도해 주세요.")
      return
    }
    // 보고 있던 대화를 지웠으면 화면에서도 지운다.
    if (meta?.id === conversationId) resetConversation()
  }

  return {
    // 상태
    isGuest,
    input,
    turns,
    meta,
    pendingQuestion,
    stage,
    running,
    inputError,
    cancelledNote,
    historyError,
    codePoints,
    overLimit,
    canSend,
    guestRemaining,
    guestLimitReached,
    externalNoticeAcknowledged,
    saving,
    hasUnsent,
    hasConversation,
    confirmingNewChat,
    storage,
    blocker,
    // 동작
    setInput,
    submit,
    retry,
    cancelQuestion,
    acknowledgeExternalNotice,
    requestNewChat,
    confirmNewChat,
    dismissNewChat,
    grantStorage,
    deleteAllConversations,
    revokeStorage,
    openConversation,
    removeConversation,
  }
}

export type ChatSession = ReturnType<typeof useChatSession>
