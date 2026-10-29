/*
 * 담당: [A] | 책임: 첫 화면(W-00) 카드 영역에 들어가는 AI 대화창(W-07 기능을 첫 화면에서 쓴다).
 * 근거: #210. 사용자 요청 — 페이지 수를 줄이려고 AI 질문 페이지를 첫 화면으로 옮긴다.
 *   시안 https://claude.ai/artifact/T6VdodQVFJ3thyx4zpMyyN 1·3·4번(사용자 확인).
 * 구현: 동작은 useChatSession(#207)이 맡고, 이 파일은 첫 화면에 맞는 모양만 그린다.
 *   - 위쪽 한 줄: 제목(h2, 첫 화면 h1 아래), [이전 대화](저장 중일 때만), [새 대화], 저장 상태·[저장 설정](#197 모달)
 *   - 대화 영역: 높이가 정해진 상자 안에서만 스크롤해 첫 화면이 길어지지 않게 한다. 새 메시지가 오면 맨 아래로 내린다.
 *   - 질문창: 맨 아래 고정. 개인정보 경고·첫 외부 전송 안내·하루 한도 안내·n/200·남은 횟수를 /ai와 같은 규칙으로 보인다.
 *   - [이전 대화]를 열었을 때만 목록과 [대화 기록 삭제]·[동의 철회]를 보인다(위쪽 줄을 단순하게 유지).
 *   - 말풍선·출처·S6/S7/S9 안내는 공용 부품(chat-parts.tsx, #223)을 써 /ai와 모양·문구가 같다.
 *   - #214: 대화창 위에 자주 묻는 예시 질문 칩. 누르면 질문창에 담고 초점을 옮긴다(보내지 않음).
 *   - #227(새 시안 https://claude.ai/artifact/TuiF5t6g7WzBoez9bxFWov, 모양만 변경): 위쪽 줄 버튼·저장 상태를
 *     같은 크기로 맞추고, 개인정보 경고와 첫 외부 전송 안내를 한 줄로 합쳤다. 질문창은 한 줄 높이, 대화 상자는
 *     최대 420px(화면 높이 62%)로 줄였다. 보내기 조건·저장 동의·확인창 등 동작은 그대로다.
 * 제한사항: 확인창 문구는 /ai와 같다.
 */
import { History, MessageCircle, Send, Square, SquarePen, TriangleAlert } from "lucide-react"
import { useCallback, useEffect, useId, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Notice } from "@/components/ui/notice"
import { useStorageActions } from "@/components/ui/storage-controls"
import { selectNamespace, useAuthStore } from "@/features/auth/auth-store"
import { createMockAskResponse } from "@/mocks/ai-stream"
import { useMockAiScenarioStore } from "@/mocks/mock-ai-scenario"
import { USE_MOCK_API } from "@/shared/api/data-source"
import { GUEST_DAILY_LIMIT, PRIVACY_WARNING, SSE_STAGE_LABELS } from "@/shared/content/chat"
import { DELETE_BUTTON_LABELS } from "@/shared/content/checklist"
import { CHAT_INPUT_POLICY } from "@/shared/contracts/ui"
import type { StorageNamespace } from "@/shared/storage/db"
import { createApiAskTransport } from "./ask-transport"
import {
  CHAT_POLICY_ITEMS,
  CHAT_TOOL_BUTTON_CLASS,
  ChatConsentBand,
  PreviousConversations,
} from "./chat-history"
import {
  AnsweredBubble,
  EXTERNAL_TRANSFER_NOTICE,
  FailureBubble,
  GuestLimitNotice,
  MAX_MANUAL_RETRIES,
  WithheldBubble,
} from "./chat-parts"
import { useChatSessionStore } from "./chat-store"
import { ExampleQuestions } from "./example-questions"
import { useChatSession } from "./use-chat-session"
import type { ChatTransport } from "./use-chat-stream"

const apiAskTransport = createApiAskTransport()

// Mock 모드: 비로그인 남은 횟수가 0이면 서버처럼 429를 돌려준다(chat-page.tsx와 같은 규칙). 실제 모드: A08로 보낸다.
function useHomeChatTransport(): ChatTransport {
  const isGuest = useAuthStore((s) => s.accountId === null)
  const guestRemaining = useChatSessionStore((s) => s.guestRemaining)
  const scenario = useMockAiScenarioStore((s) => s.scenario)
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
  return USE_MOCK_API ? mockTransport : apiAskTransport
}

// 로그인 계정(저장 영역)이 바뀌면 대화창 전체를 새로 그린다(P1). 이전 계정의 대화·입력·진행 중 요청이 함께 정리된다.
export function HomeChatWindow() {
  const namespace = useAuthStore(selectNamespace)
  return <HomeChatScreen key={namespace} namespace={namespace} />
}

function HomeChatScreen({ namespace }: { namespace: StorageNamespace }) {
  const transport = useHomeChatTransport()
  const chat = useChatSession({ namespace, transport })
  const [historyOpen, setHistoryOpen] = useState(false)
  const titleId = useId()
  const inputId = useId()
  const counterId = useId()
  const messagesRef = useRef<HTMLElement>(null)
  const { storage, blocker } = chat

  // 새 질문·진행 단계·답변이 생기면 대화 상자 맨 아래로 내린다(상자 안에서만 스크롤).
  const turnCount = chat.turns.length
  // biome-ignore lint/correctness/useExhaustiveDependencies: 위 값들이 바뀔 때만 내리려고 의존성으로 둔다.
  useEffect(() => {
    const box = messagesRef.current
    if (box) box.scrollTop = box.scrollHeight
  }, [turnCount, chat.pendingQuestion, chat.stage])

  // 저장을 그만두면(삭제·철회) 이전 대화 목록을 닫는다. 결과 안내는 목록을 닫아도 계속 보인다.
  const closeHistoryAfter = (action: () => Promise<boolean>) => () => {
    setHistoryOpen(false)
    return action()
  }
  // #227: [대화 기록 삭제]는 [이전 대화] 안에, [저장 동의 철회]는 "✓ 저장 중"을 눌러 여는 저장 설정 모달 안에 둔다.
  //   확인창·결과 안내·재시도는 전과 같은 공용 동작(useStorageActions)이다.
  const historyActions = useStorageActions({
    itemName: "AI 대화 기록",
    deleteTitle: "AI 대화 기록을 삭제할까요?",
    revokeTitle: "AI 대화 저장 동의를 철회할까요?",
    onDelete: closeHistoryAfter(chat.deleteAllConversations),
    onRevoke: closeHistoryAfter(chat.revokeStorage),
  })

  // 예시 질문을 누르면 질문창에 담고, 바로 고쳐 쓰거나 보낼 수 있게 질문창으로 초점을 옮긴다(#214).
  const pickExample = (question: string) => {
    chat.setInput(question)
    document.getElementById(inputId)?.focus()
  }

  return (
    <div className="space-y-3">
      <ExampleQuestions onPick={pickExample} />
      {/* 높이는 최신 시안대로 최대 576px(36rem), 낮은 화면에서는 화면 높이의 80%. 대화는 이 상자 안에서만 스크롤한다. */}
      <section
        aria-labelledby={titleId}
        className="flex h-[min(36rem,80dvh)] flex-col overflow-hidden rounded-xl border bg-card shadow-sm"
      >
        {/* 위쪽 한 줄: 제목과 도구. 버튼·저장 상태는 모두 같은 크기(CHAT_TOOL_BUTTON_CLASS)다. */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2 sm:px-4">
          <h2 id={titleId} className="flex items-center gap-2 font-semibold leading-none">
            <MessageCircle className="size-4 text-muted-foreground" aria-hidden />
            AI에게 질문하기
          </h2>
          <div className="flex flex-wrap items-center gap-1.5">
            {chat.saving && (
              <Button
                variant="outline"
                size="sm"
                className={CHAT_TOOL_BUTTON_CLASS}
                aria-expanded={historyOpen}
                onClick={() => setHistoryOpen((open) => !open)}
              >
                <History className="size-3.5" aria-hidden />
                이전 대화 {historyOpen ? "▴" : "▾"}
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              className={CHAT_TOOL_BUTTON_CLASS}
              onClick={chat.requestNewChat}
              disabled={chat.turns.length === 0 && !chat.running && !chat.hasUnsent}
            >
              <SquarePen className="size-3.5" aria-hidden />새 대화
            </Button>
            <ChatConsentBand
              status={storage.status}
              declined={storage.declined}
              onGrant={chat.grantStorage}
              onDecline={storage.decline}
              onRevoke={() => historyActions.request("revoke")}
            />
          </div>
        </div>

        {/* 이전 대화 목록과 삭제·철회. 열었을 때만 보인다. 결과 안내는 목록을 닫아도 남는다. */}
        <div className="space-y-2 px-4 has-[p,ul,button]:py-2">
          {chat.saving && historyOpen && (
            <section aria-label="이전 대화 목록" className="max-h-40 space-y-2 overflow-y-auto">
              <PreviousConversations
                conversations={storage.conversations}
                currentId={chat.meta?.id ?? null}
                onOpen={(conversation) => {
                  setHistoryOpen(false)
                  void chat.openConversation(conversation)
                }}
                onRemove={(conversation) => void chat.removeConversation(conversation.id)}
              />
            </section>
          )}
          {chat.saving && historyOpen && (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={historyActions.busy}
                onClick={() => historyActions.request("delete")}
              >
                {DELETE_BUTTON_LABELS.chat}
              </Button>
            </div>
          )}
          {historyActions.view}
          {chat.historyError && <Notice tone="danger">{chat.historyError}</Notice>}
        </div>

        {/* 대화: 상자 안에서만 스크롤 */}
        <section
          ref={messagesRef}
          aria-label="대화"
          aria-live="polite"
          className="flex flex-1 flex-col gap-4 overflow-y-auto px-3 py-4 sm:px-4"
        >
          {chat.turns.length === 0 && !chat.pendingQuestion && (
            <p className="m-auto text-base text-muted-foreground">궁금한 것을 물어보세요.</p>
          )}
          {chat.turns.map((turn) => (
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
                  isGuest={chat.isGuest}
                  canRetry={turn.retries < MAX_MANUAL_RETRIES}
                  busy={chat.running}
                  onRetry={() => chat.retry(turn)}
                />
              )}
            </div>
          ))}
          {chat.pendingQuestion && (
            <div className="space-y-2">
              <p className="ml-auto w-fit max-w-[85%] rounded-xl bg-primary px-4 py-2 text-primary-foreground">
                {chat.pendingQuestion}
              </p>
              <div
                role="status"
                className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-4 text-sm"
              >
                <span className="size-2 animate-pulse rounded-full bg-primary" aria-hidden />
                {chat.stage ? SSE_STAGE_LABELS[chat.stage] : "질문을 보내는 중"}…
                <Button size="sm" variant="outline" onClick={chat.cancelQuestion}>
                  <Square className="size-3.5" />
                  취소
                </Button>
              </div>
            </div>
          )}
          {chat.cancelledNote && (
            <p className="text-sm text-muted-foreground">
              질문을 취소했습니다. 입력칸에 질문이 남아 있습니다.
            </p>
          )}
        </section>

        {/* 질문창: 맨 아래 고정 */}
        <form
          onSubmit={(event) => {
            event.preventDefault()
            chat.submit()
          }}
          className="space-y-2 border-t px-3 py-3 sm:px-4"
        >
          {/* 개인정보 경고(항상 보임)와 처음 외부 전송 안내를 한 줄로 보인다(시안). [확인]을 누르기 전에는 보낼 수
              없고, 누르면 외부 전송 안내와 [확인]만 사라지고 경고는 남는다(PRD 3-1-2, 동작은 전과 같다). */}
          <div className="flex items-center gap-2 text-sm text-warning-foreground">
            <TriangleAlert className="size-4 shrink-0" aria-hidden />
            <p className="min-w-0 flex-1">
              <span>{PRIVACY_WARNING}</span>
              {!chat.externalNoticeAcknowledged && <span> {EXTERNAL_TRANSFER_NOTICE}</span>}
            </p>
            {!chat.externalNoticeAcknowledged && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 shrink-0 px-3 text-sm"
                onClick={chat.acknowledgeExternalNotice}
              >
                확인
              </Button>
            )}
          </div>
          {chat.guestLimitReached && <GuestLimitNotice isGuest />}
          <div className="flex items-end gap-2">
            <label htmlFor={inputId} className="sr-only">
              질문
            </label>
            <textarea
              id={inputId}
              value={chat.input}
              onChange={(event) => chat.setInput(event.target.value)}
              // 시안: 한 줄 높이로 줄여 대화 영역을 넓힌다. 긴 질문은 칸 안에서 스크롤된다.
              rows={1}
              placeholder="예: 상속포기 기한이 언제부터인가요?"
              aria-describedby={counterId}
              aria-invalid={chat.overLimit || Boolean(chat.inputError)}
              className="min-h-11 min-w-0 flex-1 resize-none rounded-md border border-input bg-transparent px-3 py-2.5 text-base shadow-xs outline-none placeholder:text-muted-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
            />
            <Button type="submit" className="h-11 shrink-0" disabled={!chat.canSend}>
              <Send className="size-4" />
              {/* 아주 좁은 화면(360px 미만)에서는 아이콘만 보이고, 이름은 화면낭독기에 그대로 읽힌다. */}
              <span className="max-[359px]:sr-only">보내기</span>
            </Button>
          </div>
          <p
            id={counterId}
            className={
              chat.overLimit ? "text-xs text-danger-foreground" : "text-xs text-muted-foreground"
            }
          >
            {chat.codePoints}/{CHAT_INPUT_POLICY.maxQuestionCodePoints}자
            {chat.overLimit && " · 200자를 넘었습니다. 줄여 주세요."}
            {chat.isGuest &&
              chat.guestRemaining !== null &&
              ` · 오늘 남은 질문 ${chat.guestRemaining}회 (비로그인)`}
          </p>
          {chat.inputError && (
            <p role="alert" className="text-sm text-danger-foreground">
              {chat.inputError}
            </p>
          )}
        </form>

        {/* S8 새 대화 확인(/ai와 같은 문구) */}
        {chat.confirmingNewChat && (
          <ConfirmDialog
            title={
              chat.saving
                ? "보내지 않은 입력이 있습니다. 새 대화를 시작할까요?"
                : "이 대화는 저장되지 않아 새 대화를 시작하면 사라집니다."
            }
            actions={[{ label: "새 대화 시작", primary: true, onClick: chat.confirmNewChat }]}
            onCancel={chat.dismissNewChat}
          />
        )}

        {/* S11 저장 안 된 대화 이탈 확인(/ai와 같은 문구) */}
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
                        if (await chat.grantStorage()) blocker.proceed()
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
      </section>
    </div>
  )
}
