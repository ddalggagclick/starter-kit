/*
 * 담당: [A] | 책임: W-04 절차 상세 화면.
 * PRD: E2 / 스토리 2-3 / 태스크 2-3-1, 2-3-2.
 * 구현: 바로 할 행동·기한·위험·담당 기관은 접을 수 없게 항상 펼친다. 서류·방법·예외·문의는
 *   <details> 접기형(키보드 Enter/Space로 열고 닫음). 4건 이상이면 처음에 접는다(원고 1장, 명세서 8-4절).
 *   공식 출처 링크와 "공식 링크에서 직접 확인" 문구는 항상 보인다.
 * 근거 콘텐츠: W-04 공식 안내 원고 p01~p08 (김현주, 2026-10-22) → mocks/procedures.ts.
 * 완료 기준: 접기 상태와 관계없이 행동·기한·위험·기관이 보인다.
 * 제한사항: 출처 없는 사실을 추가하지 않는다. 재방문 접힘 상태(M-10)는 미결정이다.
 */
import { ArrowLeft, ExternalLink } from "lucide-react"
import { Link, useParams } from "react-router"
import { Notice } from "@/components/ui/notice"
import { FeedbackMockButton } from "@/features/reports/feedback-mock-dialog"
import { COMMON_RISK_WARNING } from "@/mocks/checklist"
import {
  CHECK_OFFICIAL_SOURCE,
  findProcedureName,
  OFFICIAL_LINK_GAP_NOTES,
  PROCEDURE_CONTENT_STATUS,
} from "@/mocks/procedures"
import type { ProcedureDetailWire } from "@/shared/api/types"
import { useProcedureDetail } from "./api"
import { GuidanceReadToggle, RecheckBadge } from "./guidance-read-toggle"

// 원고 1장·명세서 8-4절: 서류·방법·예외·문의처는 4건 이상이면 접는다(화면 시험 뒤 팀이 바꿀 수 있음).
// 재방문 때 접힘 상태 유지 여부(M-10)는 미결정이라 정하지 않는다.
export const COLLAPSE_MIN_ITEMS = 4
export const isCollapsedByDefault = (itemCount: number) => itemCount >= COLLAPSE_MIN_ITEMS

const ALWAYS_OPEN: { key: "action" | "deadline" | "risk" | "agency"; label: string }[] = [
  { key: "action", label: "바로 할 행동" },
  { key: "deadline", label: "기한" },
  { key: "risk", label: "위험 · 주의" },
  { key: "agency", label: "담당 기관" },
]

const OPTIONAL: { key: "documents" | "methods" | "exceptions" | "contacts"; label: string }[] = [
  { key: "documents", label: "필요 서류" },
  { key: "methods", label: "신청 방법" },
  { key: "exceptions", label: "예외 · 참고" },
  { key: "contacts", label: "문의처" },
]

function ProcedureBody({ detail }: { detail: ProcedureDetailWire }) {
  return (
    <>
      <section aria-label="항상 표시되는 핵심 안내" className="grid gap-3 sm:grid-cols-2">
        {ALWAYS_OPEN.map(({ key, label }) => (
          <div
            key={key}
            className={
              key === "deadline" || key === "risk"
                ? "rounded-xl border border-warning-foreground/20 bg-warning p-4"
                : "rounded-xl border bg-card p-4"
            }
          >
            <h2 className="text-sm font-semibold text-muted-foreground">{label}</h2>
            <p className="mt-1 leading-7">{detail[key] ?? "공식 자료에서 확인하세요."}</p>
          </div>
        ))}
      </section>

      <section aria-label="자세한 안내" className="space-y-2">
        {OPTIONAL.map(({ key, label }) => {
          const items = detail[key] ?? []
          if (items.length === 0) return null
          return (
            <details
              key={key}
              open={!isCollapsedByDefault(items.length)}
              className="group rounded-xl border bg-card"
            >
              <summary className="cursor-pointer list-none px-4 py-3 font-medium focus-visible:ring-2 focus-visible:ring-ring">
                <span className="mr-2 inline-block transition-transform group-open:rotate-90">
                  ›
                </span>
                {label} ({items.length})
              </summary>
              <ul className="list-disc space-y-1 px-9 pb-4 text-sm leading-6">
                {items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </details>
          )
        })}
      </section>

      <section aria-label="공식 출처" className="space-y-2 rounded-xl border bg-card p-4">
        <h2 className="font-semibold">공식 출처에서 직접 확인</h2>
        <p className="text-sm">{CHECK_OFFICIAL_SOURCE}</p>
        <ul className="space-y-1">
          {(detail.officialLinks ?? []).map((link) => (
            <li key={link.url}>
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm underline underline-offset-4"
              >
                {link.title}
                <ExternalLink className="size-3.5" aria-hidden />
                <span className="sr-only">(새 창)</span>
              </a>
            </li>
          ))}
        </ul>
        {detail.procedureId && OFFICIAL_LINK_GAP_NOTES[detail.procedureId] && (
          <p className="text-sm text-muted-foreground">
            {OFFICIAL_LINK_GAP_NOTES[detail.procedureId]}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          {PROCEDURE_CONTENT_STATUS}. 개인의 기한·자격·법적 효과를 판단하지 않습니다.
        </p>
      </section>

      {(detail.relatedProcedureIds ?? []).length > 0 && (
        <section aria-label="함께 보면 좋은 절차" className="space-y-2">
          <h2 className="font-semibold">함께 보면 좋은 절차</h2>
          <div className="flex flex-wrap gap-2">
            {(detail.relatedProcedureIds ?? []).map((id) => (
              <Link
                key={id}
                to={`/procedures/${id}`}
                className="rounded-full border bg-card px-3 py-1.5 text-sm hover:bg-muted"
              >
                {findProcedureName(id)}
              </Link>
            ))}
          </div>
        </section>
      )}
    </>
  )
}

export function ProcedureDetailPage() {
  const { procedureId = "" } = useParams()
  const { data, isPending, isError } = useProcedureDetail(procedureId)

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        to="/procedures"
        className="inline-flex items-center gap-1 text-sm underline-offset-4 hover:underline"
      >
        <ArrowLeft className="size-4" aria-hidden />
        전체 절차
      </Link>
      {isPending && <p role="status">상세 안내를 불러오는 중…</p>}
      {isError && (
        <Notice tone="danger">
          찾을 수 없는 절차입니다. 전체 절차 목록에서 다시 선택해 주세요.
        </Notice>
      )}
      {data?.procedureId && (
        <>
          <div className="space-y-2">
            <p className="text-sm font-semibold text-muted-foreground">W-04 · 공식 절차 상세</p>
            <h1 className="flex flex-wrap items-center gap-2 text-2xl font-bold">
              {findProcedureName(data.procedureId)}
              <RecheckBadge procedureId={data.procedureId} />
            </h1>
          </div>
          <Notice tone="warning">{COMMON_RISK_WARNING}</Notice>
          <ProcedureBody detail={data} />
          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
            <GuidanceReadToggle procedureId={data.procedureId} variant="detail" />
            <FeedbackMockButton context={`W-04 ${data.procedureId}`} />
          </div>
        </>
      )}
    </div>
  )
}
