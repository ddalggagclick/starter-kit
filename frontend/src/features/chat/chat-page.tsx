/*
 * 담당: [A] | 책임: W-07 AI 질문 화면(S1 입력 · S2 진행 · S3 답변 · S6 기술 오류 · S7 판단 유보 · S9 사용 제한).
 * PRD: E3 / 태스크 3-1-1, 3-1-2, 3-1-5, 3-4-3, 3-4-4, 3-5-1, 3-5-4, 5-6-2. 화면정의서 v1.4 08·14장.
 * 구현: 200 코드 포인트 입력·글자 수, 예시 질문은 입력칸만 채움, 개인정보 경고 상시 표시, 최초 외부 전송 안내,
 *   실제 status 이벤트로 진행 표시, 검증된 답변만 자동 타이핑, 출처 2개 + '추가 출처 보기', 취소,
 *   S6은 질문을 남기고 다시 시도, 비로그인 10회 소진(S9)이면 로그인·회원가입 진입.
 * 제한사항: V1은 Mock SSE다(Gemini·RAG 호출 없음). 화면 상단에 Mock임을 표시하고 실동작 완료로 보이지 않게 한다.
 *   대화 저장 동의·이전 대화(S10)·이탈 확인(S11)은 2구간(간트 19·21)이다.
 */
import { ExternalLink, Send, Square } from "lucide-react"
import { type FormEvent, useCallback, useId, useState } from "react"
import { Link, useLocation } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import { useAuthStore } from "@/features/auth/auth-store"
import {
  createMockAskResponse,
  MOCK_AI_SCENARIO_LABELS,
  MOCK_EXAMPLE_QUESTIONS,
  type MockAiScenario,
  PRIVACY_WARNING,
  SSE_STAGE_LABELS,
  WITHHELD_COPY,
} from "@/mocks/ai-stream"
import type { ApiFailure } from "@/shared/api/api-error"
import type { SseResultEvent } from "@/shared/api/types"
import { CHAT_INPUT_POLICY, countUnicodeCodePoints } from "@/shared/contracts/ui"
import { useChatSessionStore } from "./chat-store"
import { type ChatOutcome, type ChatTransport, useChatStream } from "./use-chat-stream"
import { useTypewriter } from "./use-typewriter"

const VISIBLE_SOURCE_COUNT = 2

// 문구 검토(P02) 전 Mock 문구다. 외부 공급자 이름은 공개 문구 확정 후 바꾼다.
export const EXTERNAL_TRANSFER_NOTICE =
  "질문 내용은 답변을 만들기 위해 외부 AI 서비스로 전송됩니다. 이름·주민등록번호·연락처 같은 개인정보는 입력하지 마세요."

type Turn = { id: number; question: string; outcome: ChatOutcome }

function Sources({ sources }: { sources: NonNullable<SseResultEvent["sources"]> }) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? sources : sources.slice(0, VISIBLE_SOURCE_COUNT)
  const hidden = sources.length - VISIBLE_SOURCE_COUNT
  return (
    <div className="space-y-1 border-t pt-2">
      <p className="text-xs font-semibold text-muted-foreground">공식 출처</p>
      <ul className="space-y-1">
        {visible.map((source) => (
          <li key={`${source.title}-${source.url}`}>
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm underline underline-offset-4"
            >
              {source.title}
              <ExternalLink className="size-3.5" aria-hidden />
              <span className="sr-only">(새 창)</span>
            </a>
          </li>
        ))}
      </ul>
      {hidden > 0 && !expanded && (
        <button type="button" className="text-sm underline" onClick={() => setExpanded(true)}>
          추가 출처 보기 ({hidden})
        </button>
      )}
    </div>
  )
}

function AnsweredBubble({ result }: { result: SseResultEvent }) {
  const { shown, done } = useTypewriter(result.answer ?? "")
  return (
    <div className="space-y-3 rounded-xl border bg-card p-4" aria-busy={!done}>
      <p className="whitespace-pre-wrap leading-7">{shown}</p>
      {done && <Sources sources={result.sources ?? []} />}
    </div>
  )
}

function FailureBubble({
  failure,
  isGuest,
  onRetry,
}: {
  failure: ApiFailure
  isGuest: boolean
  onRetry: () => void
}) {
  const location = useLocation()
  // S9 비로그인 하루 제한 (A08 429 RATE_LIMITED)
  if (failure.code === "RATE_LIMITED") {
    return (
      <Notice tone="warning" className="space-y-2">
        <p className="font-semibold">오늘 사용할 수 있는 AI 질문을 모두 사용했습니다.</p>
        {isGuest ? (
          <>
            <p>
              로그인하면 계속 질문할 수 있습니다. 체크리스트와 절차 안내는 그대로 이용할 수
              있습니다.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm">
                <Link to="/login" state={{ from: location.pathname }}>
                  로그인
                </Link>
              </Button>
              <Button size="sm" variant="outline" disabled title="회원가입은 준비 중입니다">
                회원가입 (준비 중)
              </Button>
            </div>
          </>
        ) : (
          <p>내일 다시 이용해 주세요.</p>
        )}
      </Notice>
    )
  }
  // S9 공급자 제한 — 자동 재시도하지 않는다.
  if (failure.code === "PROVIDER_RATE_LIMIT") {
    return (
      <Notice tone="warning" className="space-y-2">
        <p className="font-semibold">지금은 AI 질문이 많아 답변하지 못했습니다.</p>
        <p>잠시 후 다시 시도해 주세요.</p>
        <Button size="sm" variant="outline" onClick={onRetry}>
          다시 시도
        </Button>
      </Notice>
    )
  }
  // S6 기술 오류 — 질문은 그대로 두고 사용자가 원할 때 다시 시도한다(3-5-4).
  return (
    <Notice tone="danger" className="space-y-2">
      <p className="font-semibold">일시적인 문제로 답변하지 못했습니다.</p>
      <p>질문은 그대로 남아 있습니다. 다시 시도해 주세요.</p>
      <Button size="sm" variant="outline" onClick={onRetry}>
        다시 시도
      </Button>
    </Notice>
  )
}

function WithheldBubble() {
  return (
    <Notice tone="info" className="space-y-1">
      <p className="font-semibold">{WITHHELD_COPY.message}</p>
      <p>{WITHHELD_COPY.agencies}</p>
      <a
        href={WITHHELD_COPY.link.url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 underline underline-offset-4"
      >
        {WITHHELD_COPY.link.title}
        <ExternalLink className="size-3.5" aria-hidden />
        <span className="sr-only">(새 창)</span>
      </a>
    </Notice>
  )
}

export function ChatPage() {
  const isGuest = useAuthStore((s) => s.accountId === null)
  const {
    externalNoticeAcknowledged,
    acknowledgeExternalNotice,
    guestRemaining,
    setGuestRemaining,
  } = useChatSessionStore()
  const [scenario, setScenario] = useState<MockAiScenario>("answered")
  const [input, setInput] = useState("")
  const [turns, setTurns] = useState<Turn[]>([])
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [inputError, setInputError] = useState<string | null>(null)
  const [cancelledNote, setCancelledNote] = useState(false)
  const inputId = useId()
  const counterId = useId()

  // V1 Mock 전송. 비로그인 남은 횟수가 0이면 서버처럼 429를 돌려준다.
  const transport = useCallback<ChatTransport>(
    (request, signal) =>
      createMockAskResponse(request, {
        scenario: isGuest && guestRemaining <= 0 ? "guestLimit" : scenario,
        signal,
        remainingToday: isGuest ? Math.max(guestRemaining - 1, 0) : null,
      }),
    [isGuest, guestRemaining, scenario],
  )
  const { ask, cancel, running, stage } = useChatStream(transport)

  const codePoints = countUnicodeCodePoints(input)
  const overLimit = codePoints > CHAT_INPUT_POLICY.maxQuestionCodePoints
  async function send(question: string, earlierTurns: Turn[]) {
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
      setInputError(outcome.failure.message ?? "질문을 확인해 주세요.")
      setInput(question)
      return
    }
    if (outcome.kind !== "error" && isGuest && typeof outcome.result.remainingToday === "number") {
      setGuestRemaining(outcome.result.remainingToday)
    }
    if (outcome.kind === "error" && outcome.failure.code === "RATE_LIMITED" && isGuest) {
      setGuestRemaining(0)
    }
    setTurns((current) => [...current, { id: Date.now(), question, outcome }])
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    const question = input.trim()
    if (!question) {
      setInputError("질문을 입력해 주세요.")
      return
    }
    if (overLimit || running) return
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

  function startNewChat() {
    cancel()
    setTurns([])
    setPendingQuestion(null)
    setCancelledNote(false)
    setInputError(null)
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-muted-foreground">W-07 · AI 질문</p>
          <h1 className="text-2xl font-bold">상속 절차를 물어보세요</h1>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={startNewChat}
          disabled={turns.length === 0 && !running}
        >
          새 대화 시작
        </Button>
      </div>

      <Notice tone="info">
        V1 Mock 화면입니다. 실제 AI(Gemini)·공식자료 검색을 호출하지 않고 미리 준비한 예시 응답을
        보여줍니다.
      </Notice>

      <label className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-sm">
        <span className="font-medium">Mock 시나리오 (발표용)</span>
        <select
          value={scenario}
          onChange={(event) => setScenario(event.target.value as MockAiScenario)}
          className="h-8 rounded-md border bg-background px-2"
        >
          {Object.entries(MOCK_AI_SCENARIO_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

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
            {turn.outcome.kind === "answered" && <AnsweredBubble result={turn.outcome.result} />}
            {turn.outcome.kind === "withheld" && <WithheldBubble />}
            {turn.outcome.kind === "error" && (
              <FailureBubble
                failure={turn.outcome.failure}
                isGuest={isGuest}
                onRetry={() => {
                  const remaining = turns.filter((item) => item.id !== turn.id)
                  setTurns(remaining)
                  void send(turn.question, remaining)
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
            {isGuest && ` · 오늘 남은 질문 ${guestRemaining}회 (비로그인)`}
          </p>
          <Button type="submit" disabled={running || overLimit || !externalNoticeAcknowledged}>
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
    </div>
  )
}
