/*
 * 담당: [A] | 책임: W-04 절차 상세 화면.
 * PRD: E2 / 스토리 2-3 / 태스크 2-3-1, 2-3-2.
 * 구현: 바로 할 행동·기한·위험·담당 기관은 접을 수 없게 항상 펼친다. 서류·방법·예외·문의는
 *   <details> 접기형(키보드 Enter/Space로 열고 닫음). 공식 출처 링크는 항상 보인다.
 * 완료 기준: 접기 상태와 관계없이 행동·기한·위험·기관이 보인다.
 * 제한사항: 출처 없는 사실을 추가하지 않는다. 선택 섹션의 처음·재방문 접힘 정책은 M-10 미결정이다.
 */
import { ArrowLeft, ExternalLink } from "lucide-react"
import { Link, useParams } from "react-router"
import { Notice } from "@/components/ui/notice"
import { FeedbackMockButton } from "@/features/reports/feedback-mock-dialog"
import { COMMON_RISK_WARNING } from "@/mocks/checklist"
import { findProcedureName } from "@/mocks/procedures"
import type { ProcedureDetailWire } from "@/shared/api/types"
import { useProcedureDetail } from "./api"
import { GuidanceReadToggle, RecheckBadge } from "./guidance-read-toggle"

// M-10 결정 전 잠정값이다. 확정이 아니며, 결정되면 이 값과 재방문 처리만 바꾼다.
export const OPTIONAL_SECTION_DEFAULT_OPEN = false

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
              open={OPTIONAL_SECTION_DEFAULT_OPEN}
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
        <p className="text-xs text-muted-foreground">
          기관 대표 주소입니다. 세부 페이지와 문구는 검수 전 예시(Mock)입니다.
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
            <GuidanceReadToggle procedureId={data.procedureId} />
            <FeedbackMockButton context={`W-04 ${data.procedureId}`} />
          </div>
        </>
      )}
    </div>
  )
}
