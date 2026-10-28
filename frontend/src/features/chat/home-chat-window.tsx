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
 * 제한사항: [+더보기] 모달(⑥)은 별도 이슈다. 확인창 문구는 /ai와 같다.
 */
import { Send, Square } from "lucide-react"
import { useCallback, useEffect, useId, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Notice } from "@/components/ui/notice"
import { StorageControls } from "@/components/ui/storage-controls"
import { selectNamespace, useAuthStore } from "@/features/auth/auth-store"
import { createMockAskResponse } from "@/mocks/ai-stream"
import { useMockAiScenarioStore } from "@/mocks/mock-ai-scenario"
import { USE_MOCK_API } from "@/shared/api/data-source"
import { GUEST_DAILY_LIMIT, PRIVACY_WARNING, SSE_STAGE_LABELS } from "@/shared/content/chat"
import { DELETE_BUTTON_LABELS } from "@/shared/content/checklist"
import { CHAT_INPUT_POLICY } from "@/shared/contracts/ui"
import type { StorageNamespace } from "@/shared/storage/db"
import { createApiAskTransport } from "./ask-transport"
import { CHAT_POLICY_ITEMS, ChatConsentBand, PreviousConversations } from "./chat-history"
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

  // 저장을 그만두면(삭제·철회) 이전 대화 목록을 닫는다. 결과 안내는 StorageControls가 계속 보인다.
  const closeHistoryAfter = (action: () => Promise<boolean>) => () => {
    setHistoryOpen(false)
    return action()
  }

  // 예시 질문을 누르면 질문창에 담고, 바로 고쳐 쓰거나 보낼 수 있게 질문창으로 초점을 옮긴다(#214).
  const pickExample = (question: string) => {
    chat.setInput(question)
    document.getElementById(inputId)?.focus()
  }

  return (
    <div className="space-y-3">
      <ExampleQuestions onPick={pickExample} />
      <section
        aria-labelledby={titleId}
        className="flex h-[min(36rem,80dvh)] flex-col overflow-hidden rounded-xl border bg-card shadow-sm"
      >
        {/* 위쪽 한 줄: 제목과 도구 */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2">
          <h2 id={titleId} className="text-base font-semibold">
            AI에게 질문하기
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            {chat.saving && (
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
              onClick={chat.requestNewChat}
              disabled={chat.turns.length === 0 && !chat.running && !chat.hasUnsent}
            >
              새 대화
            </Button>
            <ChatConsentBand
              status={storage.status}
              declined={storage.declined}
              onGrant={chat.grantStorage}
              onDecline={storage.decline}
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
          <StorageControls
            available={chat.saving && historyOpen}
            itemName="AI 대화 기록"
            deleteLabel={DELETE_BUTTON_LABELS.chat}
            revokeLabel="AI 대화 저장 동의 철회"
            onDelete={closeHistoryAfter(chat.deleteAllConversations)}
            onRevoke={closeHistoryAfter(chat.revokeStorage)}
          />
          {chat.historyError && <Notice tone="danger">{chat.historyError}</Notice>}
        </div>

        {/* 대화: 상자 안에서만 스크롤 */}
        <section
          ref={messagesRef}
          aria-label="대화"
          aria-live="polite"
          className="flex-1 space-y-4 overflow-y-auto px-4 py-4"
        >
          {chat.turns.length === 0 && !chat.pendingQuestion && (
            <p className="pt-10 text-center text-muted-foreground">궁금한 것을 물어보세요.</p>
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
          className="space-y-2 border-t px-4 py-3"
        >
          <p className="text-sm text-warning-foreground">⚠ {PRIVACY_WARNING}</p>
          {!chat.externalNoticeAcknowledged && (
            <Notice tone="warning" className="flex flex-wrap items-center justify-between gap-2">
              <p>{EXTERNAL_TRANSFER_NOTICE}</p>
              <Button type="button" size="sm" onClick={chat.acknowledgeExternalNotice}>
                확인했습니다
              </Button>
            </Notice>
          )}
          {chat.guestLimitReached && <GuestLimitNotice isGuest />}
          <div className="flex items-end gap-2">
            <label htmlFor={inputId} className="sr-only">
              질문
            </label>
            <textarea
              id={inputId}
              value={chat.input}
              onChange={(event) => chat.setInput(event.target.value)}
              rows={2}
              placeholder="예: 상속포기 기한이 언제부터인가요?"
              aria-describedby={counterId}
              aria-invalid={chat.overLimit || Boolean(chat.inputError)}
              className="min-h-11 flex-1 resize-none rounded-md border border-input bg-background p-3 text-sm"
            />
            <Button type="submit" className="h-11" disabled={!chat.canSend}>
              <Send className="size-4" />
              보내기
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
