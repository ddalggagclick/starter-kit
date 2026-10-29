/*
 * 담당: [A] | 책임: AI 대화 공용 부품 — 말풍선(답변·실패·판단 유보)·하루 한도 안내·출처 목록과 대화 규칙·문구.
 * 근거: #223. /ai가 첫 화면으로 합쳐진 뒤(#211) chat-page.tsx에 섞여 있던 공용 부품만 이 파일로 옮겼다(내용 그대로).
 *   첫 화면 대화창(home-chat-window.tsx)·대화 동작 훅(use-chat-session.ts)·/ai 화면(chat-page.tsx)이 함께 쓴다.
 * PRD·규칙: 출처 2개 + '추가 출처 보기', url이 null이면 제목만, 검증된 답변만 자동 타이핑, [다시 시도] 3회(Q47),
 *   429는 message로 비로그인 하루 한도와 로그인 1분 제한을 나눔(3-7-3), S6·S7·S9 안내(7-2-2·3-7-1).
 */
import { ExternalLink } from "lucide-react"
import { useState } from "react"
import { Link, useLocation } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import type { ApiFailure } from "@/shared/api/api-error"
import { RATE_LIMIT_REASONS, type SseResultEvent } from "@/shared/api/types"
import { WITHHELD_COPY } from "@/shared/content/chat"
import { CHAT_INPUT_POLICY } from "@/shared/contracts/ui"
import { useTypewriter } from "./use-typewriter"

const VISIBLE_SOURCE_COUNT = 2
// 같은 질문의 수동 [다시 시도] 상한(최초 1회 + 3회). 새 질문 제출 횟수와는 별개다(Q47).
export const MAX_MANUAL_RETRIES = 3

// 문구 검토(P02) 전 Mock 문구다. 외부 공급자 이름은 공개 문구 확정 후 바꾼다.
// #227 새 시안: 개인정보 경고(PRIVACY_WARNING) 바로 뒤에 한 줄로 붙어 보이므로, 뜻이 겹치던
//   "이름·주민등록번호·연락처 같은 개인정보는 입력하지 마세요."는 뺐다(PRD 3-1-2: 금지 문구는 경고가 항상 보인다).
export const EXTERNAL_TRANSFER_NOTICE =
  "질문 내용은 답변을 만들기 위해 외부 AI 서비스로 전송됩니다."

// 실제 A08은 422 message에 코드 이름(VALIDATION_ERROR)을 그대로 넣는다. 코드는 사용자에게 보이지 않는다.
export const inputErrorMessage = (failure: ApiFailure): string =>
  failure.message && failure.message !== failure.code
    ? failure.message
    : `질문을 확인해 주세요. ${CHAT_INPUT_POLICY.maxQuestionCodePoints}자 이하로 입력할 수 있습니다.`

// 실제 A08은 url이 null인 출처를 보낸다(백엔드 #103). openapi 생성 타입보다 넓게 받는다.
export type ChatSource = { title?: string; url?: string | null }

export function Sources({ sources }: { sources: ChatSource[] }) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? sources : sources.slice(0, VISIBLE_SOURCE_COUNT)
  const hidden = sources.length - VISIBLE_SOURCE_COUNT
  return (
    <div className="space-y-1 border-t pt-2">
      <p className="text-xs font-semibold text-muted-foreground">공식 출처</p>
      <ul className="space-y-1">
        {visible.map((source, index) => (
          // url이 null인 출처가 여럿이면 url로 key를 만들 수 없다. 서버 순서를 그대로 쓴다.
          // biome-ignore lint/suspicious/noArrayIndexKey: 출처 목록은 순서가 바뀌지 않는 읽기 전용 목록이다.
          <li key={index}>
            {source.url ? (
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm underline underline-offset-4"
              >
                {source.title || source.url}
                <ExternalLink className="size-3.5" aria-hidden />
                <span className="sr-only">(새 창)</span>
              </a>
            ) : (
              <span className="text-sm">{source.title || "공식 출처"}</span>
            )}
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

// instant: 저장 기록에서 다시 연 답변. 이미 읽은 답이라 타이핑 효과 없이 바로 보인다.
export function AnsweredBubble({
  result,
  instant = false,
}: {
  result: SseResultEvent
  instant?: boolean
}) {
  const typed = useTypewriter(instant ? "" : (result.answer ?? ""))
  const shown = instant ? (result.answer ?? "") : typed.shown
  const done = instant || typed.done
  return (
    <div
      className="w-fit max-w-[92%] space-y-2 rounded-xl border bg-card p-4 text-base leading-7"
      aria-busy={!done}
    >
      <p className="whitespace-pre-wrap leading-7">{shown}</p>
      {done && <Sources sources={result.sources ?? []} />}
    </div>
  )
}

function RetryButton({
  onRetry,
  canRetry,
  busy,
}: {
  onRetry: () => void
  canRetry: boolean
  busy: boolean
}) {
  if (!canRetry) {
    return (
      <p className="text-sm">
        다시 시도 횟수({MAX_MANUAL_RETRIES}회)를 모두 사용했습니다. 잠시 후 새로 질문해 주세요.
      </p>
    )
  }
  return (
    // 다른 질문을 처리하는 중에는 한 화면 활성 요청 1개 규칙(Q45)에 따라 누를 수 없다.
    <Button size="sm" variant="outline" onClick={onRetry} disabled={busy}>
      다시 시도
    </Button>
  )
}

// 429 RATE_LIMITED의 제한 사유. Backend가 message로 구분해 보낸다(#138·#143).
// 사유를 모르면(사유를 보내지 않는 서버) 로그인 여부로 정한다. 로그인 사용자에게는 하루 한도가 없고 1분 제한만 있다.
export const rateLimitKind = (
  failure: ApiFailure,
  isGuest: boolean,
): "guestDaily" | "memberMinute" => {
  if (failure.message === RATE_LIMIT_REASONS.memberMinute) return "memberMinute"
  if (failure.message === RATE_LIMIT_REASONS.guestDaily) return "guestDaily"
  return isGuest ? "guestDaily" : "memberMinute"
}

// S9(사용 제한)일 때 AI만 멈추고 정적 안내는 계속 쓸 수 있음을 모든 제한 안내에 붙인다(7-2-2, 3-7-1).
export const STATIC_INFO_NOTE = "체크리스트와 절차 안내는 그대로 이용할 수 있습니다."

// S9 하루 질문 한도 안내. 429를 받았을 때와, 남은 횟수가 0이 된 순간(다음 질문 전) 모두 같은 안내를 쓴다(3-7-1, 5-6-2).
export function GuestLimitNotice({ isGuest }: { isGuest: boolean }) {
  const location = useLocation()
  return (
    <Notice tone="warning" className="space-y-2">
      <p className="font-semibold">오늘 사용할 수 있는 AI 질문을 모두 사용했습니다.</p>
      {isGuest ? (
        <>
          <p>로그인하면 계속 질문할 수 있습니다. {STATIC_INFO_NOTE}</p>
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm">
              <Link to="/login" state={{ from: location.pathname }}>
                로그인
              </Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link to="/signup">회원가입</Link>
            </Button>
          </div>
        </>
      ) : (
        <p>내일 다시 이용해 주세요. {STATIC_INFO_NOTE}</p>
      )}
    </Notice>
  )
}

export function FailureBubble({
  failure,
  isGuest,
  onRetry,
  canRetry,
  busy,
}: {
  failure: ApiFailure
  isGuest: boolean
  onRetry: () => void
  canRetry: boolean
  busy: boolean
}) {
  // S9 하루 제한 (A08 429 RATE_LIMITED). 비로그인은 429를 받으면 남은 횟수가 0이 되어 입력칸 위에 같은 안내
  // (로그인·회원가입 진입)가 뜬다. 같은 안내·버튼이 두 번 보이고 읽히지 않게 대화 안에는 한 줄만 남긴다(9번 통합 검증에서 발견).
  if (failure.code === "RATE_LIMITED") {
    // 로그인 사용자 1분 10회 초과(3-7-3). 하루 한도가 아니므로 "내일"을 말하지 않고, 잠시 뒤 직접 다시 시도하게 한다.
    // 자동 재시도는 하지 않는다. [다시 시도]는 같은 질문 3회 상한(Q47)을 그대로 따른다.
    if (rateLimitKind(failure, isGuest) === "memberMinute") {
      return (
        <Notice tone="warning" className="space-y-2">
          <p className="font-semibold">짧은 시간에 질문이 많아 잠시 멈췄습니다.</p>
          <p>1분 정도 지난 뒤 다시 질문해 주세요. {STATIC_INFO_NOTE}</p>
          <RetryButton onRetry={onRetry} canRetry={canRetry} busy={busy} />
        </Notice>
      )
    }
    // 하루 한도. 로그인 중인데 이 사유가 오면(토큰이 서버에서 인정되지 않은 경우) 서버 판단대로 하루 한도로 안내한다.
    return isGuest ? (
      <p className="text-sm text-muted-foreground">
        오늘 사용할 수 있는 AI 질문을 모두 사용해 답변하지 않았습니다.
      </p>
    ) : (
      <GuestLimitNotice isGuest={false} />
    )
  }
  // S9 공급자 제한 — 자동 재시도하지 않는다.
  if (failure.code === "PROVIDER_RATE_LIMIT") {
    return (
      <Notice tone="warning" className="space-y-2">
        <p className="font-semibold">지금은 AI 질문이 많아 답변하지 못했습니다.</p>
        <p>잠시 후 다시 시도해 주세요. {STATIC_INFO_NOTE}</p>
        <RetryButton onRetry={onRetry} canRetry={canRetry} busy={busy} />
      </Notice>
    )
  }
  // S6 기술 오류 — 질문은 그대로 두고 사용자가 원할 때 다시 시도한다(3-5-4).
  return (
    <Notice tone="danger" className="space-y-2">
      <p className="font-semibold">일시적인 문제로 답변하지 못했습니다.</p>
      <p>질문은 그대로 남아 있습니다. 다시 시도해 주세요.</p>
      <RetryButton onRetry={onRetry} canRetry={canRetry} busy={busy} />
    </Notice>
  )
}

export function WithheldBubble() {
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
