/*
 * 담당: [A] | 책임: W-07 AI 질문 화면(S1 입력 · S2 진행 · S3 답변 · S6 기술 오류 · S7 판단 유보 · S9 사용 제한).
 * PRD: E3 / 태스크 3-1-1, 3-1-2, 3-1-5, 3-4-3, 3-4-4, 3-5-1, 3-5-4, 5-6-2. 화면정의서 v1.4 08·14장.
 * 구현: 200 코드 포인트 입력·글자 수, 예시 질문은 입력칸만 채움, 개인정보 경고 상시 표시, 최초 외부 전송 안내,
 *   실제 status 이벤트로 진행 표시, 검증된 답변만 자동 타이핑, 출처 2개 + '추가 출처 보기', 취소,
 *   S6은 질문을 남기고 다시 시도, 비로그인 10회 소진(S9)이면 로그인·회원가입 진입.
 *   429 RATE_LIMITED는 message로 비로그인 하루 한도와 로그인 사용자 1분 제한을 나눠 안내한다(3-7-3).
 *   VITE_USE_MOCK_API=false면 실제 A08(ask-transport.ts)로 보낸다. 출처 url이 null이면 링크 없이 제목만 보인다.
 *   같은 질문의 [다시 시도]는 최대 3회다(결정 문서 Q47).
 *   AI 대화 저장 동의(S1, 체크리스트와 별도)·이전 대화 목록(S10)·새 대화(S8)·저장 안 된 대화 이탈 확인(S11)
 *   (PRD 4-1-1·3-6-1~3-6-3). 저장은 chat-storage.ts가 동의를 확인해 처리한다.
 * 제한사항: Mock 안내 문구와 발표용 시나리오 드롭다운은 사용자 요청으로 없앴다(#205). Mock 응답 시나리오는
 *   mocks/mock-ai-scenario.ts에서 정하며 기본은 정상 답변이다.
 *   새로고침·탭 닫기는 확인 없이 초기화한다(D-11). 저장 중이면 [대화 기록 삭제]·동의 철회를 보인다(4-3).
 */
import { Send, Square } from "lucide-react"
import { type FormEvent, useCallback, useId, useState } from "react"
import { useBlocker } from "react-router"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Notice } from "@/components/ui/notice"
import { StorageControls } from "@/components/ui/storage-controls"
import { selectNamespace, useAuthStore } from "@/features/auth/auth-store"
import { createMockAskResponse } from "@/mocks/ai-stream"
import { useMockAiScenarioStore } from "@/mocks/mock-ai-scenario"
import { USE_MOCK_API } from "@/shared/api/data-source"
import {
  GUEST_DAILY_LIMIT,
  MOCK_EXAMPLE_QUESTIONS,
  PRIVACY_WARNING,
  SSE_STAGE_LABELS,
} from "@/shared/content/chat"
import { DELETE_BUTTON_LABELS } from "@/shared/content/checklist"
import { CHAT_INPUT_POLICY, countUnicodeCodePoints } from "@/shared/contracts/ui"
import { inheritanceDb, type StorageNamespace } from "@/shared/storage/db"
import { createApiAskTransport } from "./ask-transport"
import { CHAT_POLICY_ITEMS, ChatConsentBand, PreviousConversations } from "./chat-history"
// 공용 부품·규칙은 chat-parts.tsx로 옮겼다(#223, 내용 그대로).
import {
  AnsweredBubble,
  EXTERNAL_TRANSFER_NOTICE,
  FailureBubble,
  GuestLimitNotice,
  inputErrorMessage,
  MAX_MANUAL_RETRIES,
  rateLimitKind,
  WithheldBubble,
} from "./chat-parts"
import {
  type ChatTurn,
  type ConversationMeta,
  conversationTitle,
  useChatStorage,
} from "./chat-storage"
import { useChatSessionStore } from "./chat-store"
import { type ChatTransport, useChatStream } from "./use-chat-stream"

const apiAskTransport = createApiAskTransport()

const newConversationId = () =>
  globalThis.crypto?.randomUUID?.() ?? `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`

// 로그인 계정(저장 영역)이 바뀌면 대화 화면 전체를 새로 그린다(P1). 이전 계정의 대화·입력·진행 중 요청이 한 번에
// 정리되고, 이전 화면에서 늦게 도착한 답변·이전 대화 열기 결과는 사라진 화면에만 반영되어 새 계정 화면에 나타나지 않는다.
export function ChatPage() {
  const namespace = useAuthStore(selectNamespace)
  return <ChatScreen key={namespace} namespace={namespace} />
}

function ChatScreen({ namespace }: { namespace: StorageNamespace }) {
  const isGuest = useAuthStore((s) => s.accountId === null)
  const {
    externalNoticeAcknowledged,
    acknowledgeExternalNotice,
    guestRemaining,
    setGuestRemaining,
  } = useChatSessionStore()
  // Mock 응답 시나리오. 화면 드롭다운은 없애고(#205) 시험 코드만 바꾼다. 기본은 정상 답변.
  const scenario = useMockAiScenarioStore((s) => s.scenario)
  const [input, setInput] = useState("")
  const [turns, setTurns] = useState<ChatTurn[]>([])
  // 지금 대화. 첫 질문이 끝날 때 만든다(제목 = 첫 질문 앞부분, D-14).
  const [meta, setMeta] = useState<ConversationMeta | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [confirmNewChat, setConfirmNewChat] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const storage = useChatStorage(inheritanceDb, namespace)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [inputError, setInputError] = useState<string | null>(null)
  const [cancelledNote, setCancelledNote] = useState(false)
  const inputId = useId()
  const counterId = useId()

  // Mock 모드: 비로그인 남은 횟수가 0이면 서버처럼 429를 돌려준다. 실제 모드: A08로 보낸다.
  const mockTransport = useCallback<ChatTransport>(
    (request, signal) => {
      const remaining = guestRemaining ?? GUEST_DAILY_LIMIT
      return createMockAskResponse(request, {
        scenario: isGuest && remaining <= 0 ? "guestLimit" : scenario,
        signal,
        remainingToday: isGuest ? Math.max(remaining - 1, 0) : null,
      })
    },
    [isGuest, guestRemaining, scenario],
  )
  const transport = USE_MOCK_API ? mockTransport : apiAskTransport
  const { ask, cancel, running, stage } = useChatStream(transport)

  // 남은 횟수가 0이 되면 다음 질문을 보내 429를 받기 전에 바로 안내하고 보내기를 막는다.
  // 남은 횟수를 모르면(null, 실제 A08은 아직 null) 서버의 429 응답으로 안내한다.
  const guestLimitReached = isGuest && guestRemaining === 0
  const codePoints = countUnicodeCodePoints(input)
  const overLimit = codePoints > CHAT_INPUT_POLICY.maxQuestionCodePoints
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

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    const question = input.trim()
    if (!question) {
      setInputError("질문을 입력해 주세요.")
      return
    }
    if (overLimit || running || guestLimitReached) return
    setInput("")
    void send(question, turns)
  }

  function onCancel() {
    cancel()
    // 취소한 질문은 입력칸으로 돌려준다.
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

  const saving = storage.status === "ready"
  const hasUnsent = input.trim() !== ""
  const hasConversation = turns.length > 0 || pendingQuestion !== null

  // S8: 저장 중이면 지금 대화는 이미 목록에 보관되어 확인 없이 새 대화를 연다. 미전송 입력이 있을 때만 묻는다.
  // 저장하지 않는 중이면 대화나 입력이 있을 때 묻는다(Q60).
  function startNewChat() {
    const needsConfirm = hasUnsent || (!saving && hasConversation)
    if (needsConfirm) setConfirmNewChat(true)
    else resetConversation()
  }

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
    setHistoryOpen(false)
    return action(currentIds)
  }

  // 정책 확인 후 [저장] 또는 S11 [이 기기에 저장하고 이동]: 동의와 지금 대화를 함께 저장한다.
  const grantStorage = () => storage.grant(meta, turns)

  async function openConversation(conversationId: string, title: string, createdAt: number) {
    setHistoryError(null)
    const restored = await storage.open(conversationId)
    if (!restored) {
      setHistoryError("이전 대화를 불러오지 못했습니다. 다시 시도해 주세요.")
      return
    }
    cancel()
    setPendingQuestion(null)
    setCancelledNote(false)
    setMeta({ id: conversationId, title, createdAt })
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

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-muted-foreground">W-07 · AI 질문</p>
          <h1 className="text-2xl font-bold">상속 절차를 물어보세요</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          {saving && (
            <Button
              variant="outline"
              size="sm"
              aria-expanded={historyOpen}
              onClick={() => setHistoryOpen((open) => !open)}
            >
              이전 대화 {historyOpen ? "▴" : "▾"}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={startNewChat}
            disabled={turns.length === 0 && !running && !hasUnsent}
          >
            새 대화 시작
          </Button>
        </div>
      </div>

      <ChatConsentBand
        status={storage.status}
        declined={storage.declined}
        onGrant={grantStorage}
        onDecline={storage.decline}
      />
      <StorageControls
        available={saving}
        itemName="AI 대화 기록"
        deleteLabel={DELETE_BUTTON_LABELS.chat}
        revokeLabel="AI 대화 저장 동의 철회"
        onDelete={() => clearStorage(storage.removeAll)}
        onRevoke={() => clearStorage(storage.revoke)}
      />

      {saving && historyOpen && (
        <section aria-label="이전 대화 목록" className="space-y-2 rounded-xl border bg-card p-3">
          <PreviousConversations
            conversations={storage.conversations}
            currentId={meta?.id ?? null}
            onOpen={(conversation) =>
              void openConversation(conversation.id, conversation.title, conversation.createdAt)
            }
            onRemove={(conversation) => void removeConversation(conversation.id)}
          />
        </section>
      )}
      {historyError && <Notice tone="danger">{historyError}</Notice>}

      <section aria-label="대화" aria-live="polite" className="space-y-4">
        {turns.length === 0 && !pendingQuestion && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">예시 질문을 누르면 입력칸에 채워집니다.</p>
            <div className="flex flex-wrap gap-2">
              {MOCK_EXAMPLE_QUESTIONS.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setInput(example)}
                  className="rounded-full border bg-card px-3 py-1.5 text-sm hover:bg-muted"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn) => (
          <div key={turn.id} className="space-y-2">
            <p className="ml-auto w-fit max-w-[85%] rounded-xl bg-primary px-4 py-2 text-primary-foreground">
              {turn.question}
            </p>
            {turn.outcome.kind === "answered" && (
              <AnsweredBubble result={turn.outcome.result} instant={turn.restored} />
            )}
            {turn.outcome.kind === "withheld" && <WithheldBubble />}
            {turn.outcome.kind === "error" && (
              <FailureBubble
                failure={turn.outcome.failure}
                isGuest={isGuest}
                canRetry={turn.retries < MAX_MANUAL_RETRIES}
                busy={running}
                onRetry={() => {
                  const remaining = turns.filter((item) => item.id !== turn.id)
                  setTurns(remaining)
                  void send(turn.question, remaining, turn.retries + 1)
                }}
              />
            )}
          </div>
        ))}
        {pendingQuestion && (
          <div className="space-y-2">
            <p className="ml-auto w-fit max-w-[85%] rounded-xl bg-primary px-4 py-2 text-primary-foreground">
              {pendingQuestion}
            </p>
            <div
              role="status"
              className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-4 text-sm"
            >
              <span className="size-2 animate-pulse rounded-full bg-primary" aria-hidden />
              {stage ? SSE_STAGE_LABELS[stage] : "질문을 보내는 중"}…
              <Button size="sm" variant="outline" onClick={onCancel}>
                <Square className="size-3.5" />
                취소
              </Button>
            </div>
          </div>
        )}
        {cancelledNote && (
          <p className="text-sm text-muted-foreground">
            질문을 취소했습니다. 입력칸에 질문이 남아 있습니다.
          </p>
        )}
      </section>

      <form onSubmit={onSubmit} className="space-y-2 rounded-xl border bg-card p-4">
        <p className="text-sm font-medium text-warning-foreground">⚠ {PRIVACY_WARNING}</p>
        {!externalNoticeAcknowledged && (
          <Notice tone="warning" className="space-y-2">
            <p>{EXTERNAL_TRANSFER_NOTICE}</p>
            <Button type="button" size="sm" onClick={acknowledgeExternalNotice}>
              확인했습니다
            </Button>
          </Notice>
        )}
        {guestLimitReached && <GuestLimitNotice isGuest />}
        <label htmlFor={inputId} className="sr-only">
          질문
        </label>
        <textarea
          id={inputId}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          rows={3}
          placeholder="예: 상속포기 기한이 언제부터인가요?"
          aria-describedby={counterId}
          aria-invalid={overLimit || Boolean(inputError)}
          className="w-full resize-y rounded-md border border-input bg-background p-3 text-sm"
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p
            id={counterId}
            className={
              overLimit ? "text-sm text-danger-foreground" : "text-sm text-muted-foreground"
            }
          >
            {codePoints}/{CHAT_INPUT_POLICY.maxQuestionCodePoints}자
            {overLimit && " · 200자를 넘었습니다. 줄여 주세요."}
            {isGuest &&
              guestRemaining !== null &&
              ` · 오늘 남은 질문 ${guestRemaining}회 (비로그인)`}
          </p>
          <Button
            type="submit"
            disabled={running || overLimit || !externalNoticeAcknowledged || guestLimitReached}
          >
            <Send className="size-4" />
            보내기
          </Button>
        </div>
        {inputError && (
          <p role="alert" className="text-sm text-danger-foreground">
            {inputError}
          </p>
        )}
      </form>

      {confirmNewChat && (
        <ConfirmDialog
          title={
            saving
              ? "보내지 않은 입력이 있습니다. 새 대화를 시작할까요?"
              : "이 대화는 저장되지 않아 새 대화를 시작하면 사라집니다."
          }
          actions={[
            {
              label: "새 대화 시작",
              primary: true,
              onClick: () => {
                setConfirmNewChat(false)
                resetConversation()
              },
            },
          ]}
          onCancel={() => setConfirmNewChat(false)}
        />
      )}

      {blocker.state === "blocked" && (
        <ConfirmDialog
          title="이 대화는 저장되지 않아 나가면 사라집니다."
          actions={[
            // 저장할 수 없는 브라우저면 저장 버튼을 숨긴다(부록4 S11).
            ...(storage.status === "failed"
              ? []
              : [
                  {
                    label: "이 기기에 저장하고 이동",
                    primary: true,
                    onClick: async () => {
                      if (await grantStorage()) blocker.proceed()
                    },
                  },
                ]),
            { label: "저장 없이 이동", onClick: () => blocker.proceed() },
          ]}
          onCancel={() => blocker.reset()}
        >
          {storage.status !== "failed" && (
            <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              {CHAT_POLICY_ITEMS.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          {storage.status === "failed" && (
            <p className="text-sm">⚠ 이 브라우저에서는 저장할 수 없습니다.</p>
          )}
        </ConfirmDialog>
      )}
    </div>
  )
}
