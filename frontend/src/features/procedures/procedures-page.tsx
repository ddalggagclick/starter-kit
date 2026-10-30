/*
 * 담당: [A] | 책임: W-03 전체 절차 탐색.
 * PRD: E2 / 스토리 2-2 / 태스크 2-2-3.
 * 구현: 공통 8개 절차를 같은 방식으로 나열하고 W-04 상세로 이동한다. W-02와 같은 절차 ID를 쓴다.
 * 제한사항: 자동 추천·순위·수동 정렬은 MVP 제외다. 표시 순서는 법적 우선순위가 아니다.
 */
import { ChevronRight } from "lucide-react"
import { Link } from "react-router"
import { Notice } from "@/components/ui/notice"
import { COMMON_RISK_WARNING } from "@/shared/content/checklist"
import { MOCK_DEADLINE_TAGS } from "@/shared/content/procedures"
import { procedureNumber, useProcedureList } from "./api"
import { RecheckBadge } from "./guidance-read-toggle"

export function ProceduresPage() {
  const { data, isPending, isError, refetch } = useProcedureList()
  return (
    <div className="space-y-group md:space-y-block">
      <div className="space-y-2">
        <p className="text-sm font-semibold text-muted-foreground">전체 절차</p>
        <h1 className="text-2xl font-bold">상속 공통 절차 8가지</h1>
        <p className="text-muted-foreground">
          순서는 일반적인 안내 순서이며 법적 의무의 우선순위가 아닙니다.
        </p>
      </div>
      <Notice tone="warning">{COMMON_RISK_WARNING}</Notice>
      {isPending && <p role="status">절차를 불러오는 중…</p>}
      {isError && (
        <Notice tone="danger">
          절차를 불러오지 못했습니다.{" "}
          <button type="button" className="underline" onClick={() => refetch()}>
            다시 시도
          </button>
        </Notice>
      )}
      {data && (
        <ol className="divide-y rounded-xl border bg-card">
          {data.procedures.map((procedure) => (
            <li key={procedure.procedureId}>
              <Link
                to={`/procedures/${procedure.procedureId}`}
                className="flex items-center gap-4 px-5 py-4 hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-sm font-semibold">
                  {procedureNumber(procedure.procedureId)}
                </span>
                <span className="min-w-0 flex-1 space-y-1">
                  <span className="flex flex-wrap items-center gap-2 font-medium">
                    {procedure.name}
                    {MOCK_DEADLINE_TAGS[procedure.procedureId] && (
                      <span className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground">
                        {MOCK_DEADLINE_TAGS[procedure.procedureId]} (일반 기준)
                      </span>
                    )}
                    <RecheckBadge procedureId={procedure.procedureId} />
                  </span>
                  <span className="block text-sm text-muted-foreground">{procedure.summary}</span>
                </span>
                <ChevronRight className="size-4 shrink-0" aria-hidden />
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
