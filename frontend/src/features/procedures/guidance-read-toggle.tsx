/*
 * 담당: [A] | 책임: 절차별 수동 '안내 확인'(읽음 표시) 버튼과 읽음 진행 막대(W-02 카드·W-04 상세 공용).
 * PRD: 태스크 2-5-1, 2-5-2, 2-4-3(재확인 배지).
 * 구현: 설명 문장 대신 버튼 모양·색·✓ 기호로 상태를 보여 준다(사용자 요청: 직관성 우선, 문구 최소화).
 *   누르면 "✓ 읽음", 다시 누르면 해제. 재확인 필요 상태에서는 "다시 확인하기"로 보이고 누르면 배지가 사라진다.
 *   "신청 완료가 아님"은 마우스를 올리면 뜨는 짧은 설명(title)으로만 알리고, 화면낭독기는 같은 문장을 읽는다.
 *   체크는 화면 표시만 바꾸며 카드 순서·숨김은 바꾸지 않는다(2-5-2).
 *   #227 새 시안(모양만): 체크리스트 버튼은 폭을 맞추고, 읽기 전에도 회색 ✓ 동그라미를 보여 누르면 초록이 됨을 알린다.
 *   사용자 지시: 상세 버튼 이름도 [다 읽었어요] 대신 늘 [읽음]이고, 누르면 진한 초록 바탕·흰 글자로 켜진다.
 * 제한사항: '안내 확인'은 읽음 표시이며 법원·기관 신고·신청 완료가 아니다(Q71).
 */
import { useId } from "react"
import { cn } from "@/lib/utils"
import type { ProcedureId } from "@/shared/contracts/domain"
import { countGuidance, useInheritanceStore } from "@/shared/state/inheritance-store"

export const GUIDANCE_READ_HINT = "읽었다는 표시예요. 신청·신고 완료가 아닙니다."

// variant: card = 체크리스트 카드(작게), detail = 절차 상세(크게, 읽은 개수 함께)
export function GuidanceReadToggle({
  procedureId,
  variant = "card",
}: {
  procedureId: ProcedureId
  variant?: "card" | "detail"
}) {
  const state = useInheritanceStore((s) => s.procedureStates[procedureId])
  const counts = countGuidance(useInheritanceStore((s) => s.procedureStates))
  const setGuidanceRead = useInheritanceStore((s) => s.setGuidanceRead)
  const hintId = useId()
  const read = state.guidanceRead && !state.needsRecheck
  // 최신 시안: 체크리스트 버튼은 늘 "읽음"이고 회색 → 초록으로 상태를 보인다(aria-pressed로 읽힘).
  //   상세 버튼도 늘 [읽음]이고, 켜지면 진한 초록 바탕으로 바뀐다. 재확인 필요는 제목 옆 배지로 알린다.
  const label = "읽음"

  return (
    <span className="inline-flex items-center gap-3">
      <button
        type="button"
        aria-pressed={read}
        aria-describedby={hintId}
        title={GUIDANCE_READ_HINT}
        onClick={() => setGuidanceRead(procedureId, !read)}
        className={cn(
          "inline-flex items-center gap-2 rounded-full border-2 font-medium transition-colors",
          variant === "detail"
            ? "px-4 py-1.5 text-base"
            : "min-w-[5.25rem] justify-center px-3 py-1 text-sm",
          read
            ? variant === "detail"
              ? "border-success-foreground bg-success-foreground text-white shadow-sm"
              : "border-success-foreground bg-success text-success-foreground"
            : variant === "card"
              ? "border-input bg-card text-muted-foreground hover:bg-muted"
              : "border-input bg-card text-foreground hover:bg-muted",
        )}
      >
        <span
          aria-hidden
          className={cn(
            "inline-grid size-4 place-items-center rounded-full border-2 text-[10px] leading-none",
            read
              ? variant === "detail"
                ? "border-white bg-white text-success-foreground"
                : "border-success-foreground bg-success-foreground text-card"
              : "border-input text-input",
          )}
        >
          ✓
        </span>
        {label}
      </button>
      <span id={hintId} className="sr-only">
        {GUIDANCE_READ_HINT}
      </span>
      {variant === "detail" && (
        <span role="status" className="text-sm text-muted-foreground">
          {counts.read}/{counts.total} 읽음
        </span>
      )}
    </span>
  )
}

// 체크리스트 상단 진행 막대. 문장 대신 "N/8 읽음"과 막대로 진행 정도를 보여 준다.
export function GuidanceProgress() {
  const counts = countGuidance(useInheritanceStore((s) => s.procedureStates))
  return (
    <div className="flex min-w-48 flex-1 items-center gap-3 sm:max-w-sm" aria-live="polite">
      <span className="shrink-0 text-sm font-semibold">
        {counts.read}/{counts.total} 읽음
        {counts.recheck > 0 && (
          <span className="ml-2 font-normal text-warning-foreground">
            · 재확인 {counts.recheck}
          </span>
        )}
      </span>
      <div
        role="progressbar"
        aria-label="절차 안내 읽음"
        aria-valuemin={0}
        aria-valuemax={counts.total}
        aria-valuenow={counts.read}
        className="h-2 flex-1 overflow-hidden rounded-full bg-border"
      >
        <div
          className="h-full rounded-full bg-progress transition-[width]"
          style={{ width: `${(counts.read / counts.total) * 100}%` }}
        />
      </div>
    </div>
  )
}

export function RecheckBadge({ procedureId }: { procedureId: ProcedureId }) {
  const needsRecheck = useInheritanceStore((s) => s.procedureStates[procedureId].needsRecheck)
  if (!needsRecheck) return null
  return (
    <span className="rounded-full bg-warning px-2 py-0.5 text-xs font-semibold text-warning-foreground">
      답변 변경 · 재확인 필요
    </span>
  )
}
