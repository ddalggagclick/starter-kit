/*
 * 담당: [A] | 책임: 절차별 수동 '안내 확인' 체크(W-02 카드·W-04 상세 공용).
 * PRD: 태스크 2-5-1, 2-5-2, 2-4-3(재확인 배지).
 * 구현: 체크는 화면 표시만 바꾼다. 재확인 필요 상태에서 다시 체크하면 배지가 사라진다.
 * 제한사항: '안내 확인'은 읽음 표시이며 법원·기관 신고·신청 완료가 아니다(Q71).
 */
import type { ProcedureId } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"

export function GuidanceReadToggle({ procedureId }: { procedureId: ProcedureId }) {
  const state = useInheritanceStore((s) => s.procedureStates[procedureId])
  const setGuidanceRead = useInheritanceStore((s) => s.setGuidanceRead)
  const checked = state.guidanceRead && !state.needsRecheck
  return (
    <label className="flex w-fit cursor-pointer items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => setGuidanceRead(procedureId, event.target.checked)}
      />
      {state.needsRecheck ? "다시 확인함" : "안내 확인"}
    </label>
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
