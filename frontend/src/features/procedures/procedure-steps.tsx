/*
 * 담당: [A] | 책임: [전체 절차] 모달 내용 — 공통 절차 8개를 펼쳐 보기(접기형).
 * 근거: #227 새 시안(https://claude.ai/artifact/NgrnTfYvGvuGj5PYWnJcfu) 모달 "상속 공통 절차".
 * 구현: 목록(A06)으로 이름·요약·기한 표시를 보이고, 항목을 펼칠 때만 그 절차 상세(A07)를 불러와
 *   바로 할 행동·기한·주의·담당 기관과 [상세 보기]를 보인다(8개를 한꺼번에 부르지 않는다).
 *   문구는 상세 화면과 같은 검수 원고(API 응답)를 그대로 쓴다. 공통 위험 경고는 맨 위에 항상 보인다.
 *   [체크리스트에서 내 상황 보기]는 체크리스트로 가고(이동하면 모달이 닫힌다), [닫기]는 모달만 닫는다.
 * 제한사항: 순서는 공통 안내 순서이며 법적 우선순위가 아니다. 새 안내 문장을 만들지 않는다.
 */
import { ChevronDown, ChevronRight, ListChecks, TriangleAlert } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice, WarningPill } from "@/components/ui/notice"
import { useServerChecklistStore } from "@/features/checklist/server-checklist"
import { COMMON_RISK_WARNING } from "@/shared/content/checklist"
import { MOCK_DEADLINE_TAGS } from "@/shared/content/procedures"
import type { ProcedureId } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { useOverlayStore } from "@/shared/state/overlay-store"
import { procedureNumber, useProcedureDetail, useProcedureList } from "./api"
import { RecheckBadge } from "./guidance-read-toggle"

const FALLBACK = "공식 자료에서 확인하세요."

// 펼친 항목의 핵심 안내 4개. 펼칠 때 처음 그려지므로 그때 상세를 불러온다.
function StepDetail({ procedureId }: { procedureId: ProcedureId }) {
  const { data, isPending, isError } = useProcedureDetail(procedureId)
  if (isPending)
    return (
      <p role="status" className="pb-4 pl-9 text-sm text-muted-foreground">
        상세 안내를 불러오는 중…
      </p>
    )
  if (isError || !data)
    return (
      <Notice tone="danger" className="mb-4 ml-9">
        상세 안내를 불러오지 못했습니다. [상세 보기]에서 다시 확인해 주세요.
      </Notice>
    )
  return (
    <dl className="grid gap-3 pb-4 pl-9 text-base sm:text-sm">
      <div>
        <dt className="text-xs font-medium text-muted-foreground">바로 할 행동</dt>
        <dd>{data.action ?? FALLBACK}</dd>
      </div>
      <div>
        <dt className="text-xs font-semibold text-danger-foreground">기한</dt>
        <dd>{data.deadline ?? FALLBACK}</dd>
      </div>
      <div className="rounded-lg border border-danger-foreground/20 bg-danger px-3 py-2 text-danger-foreground">
        <dt className="text-xs font-medium">주의</dt>
        <dd>{data.risk ?? FALLBACK}</dd>
      </div>
      <div>
        <dt className="text-xs font-medium text-muted-foreground">담당 기관</dt>
        <dd>{data.agency ?? FALLBACK}</dd>
      </div>
      <div>
        <Link
          to={`/procedures/${procedureId}`}
          // 사용자 요청: 눈에 띄게 굵은 글씨 + 옅은 남색 바탕의 작은 둥근 버튼. 밑줄 효과는 없다.
          className="inline-flex h-8 items-center gap-1 rounded-full bg-primary/10 px-3 text-sm font-semibold text-primary outline-none transition-colors hover:bg-primary/15 focus-visible:ring-[3px] focus-visible:ring-ring/50 max-md:min-h-11"
        >
          상세 보기
          <ChevronRight className="size-4" aria-hidden />
        </Link>
      </div>
    </dl>
  )
}

export function ProcedureSteps() {
  const { data, isPending, isError, refetch } = useProcedureList()
  const close = useOverlayStore((s) => s.close)
  const open = useOverlayStore((s) => s.open)
  // 최신 시안: 아직 답하지 않았으면 [체크리스트에서 내 상황 보기]는 질문 3개 모달로 바꾼다.
  const hasAnswers = useInheritanceStore((s) => s.answers !== null)
  const serverPending = useServerChecklistStore((s) => s.pending !== null)
  // 한 번이라도 펼친 항목만 상세를 그린다(접어도 다시 부르지 않게 남겨 둔다).
  const [opened, setOpened] = useState<ReadonlySet<ProcedureId>>(() => new Set())

  return (
    // 모달 간격 리듬: 머리말 ↔ 목록 group 20px, 제목 ↔ 설명 8px(황금비 규칙, modal.tsx).
    <div className="space-y-group">
      <div className="space-y-2 pr-8">
        <h2 className="text-lg font-semibold leading-none">상속 공통 절차</h2>
        <p className="text-sm text-muted-foreground">
          공통 안내 순서예요. 법적 우선순위가 아닙니다.
        </p>
      </div>
      <WarningPill>{COMMON_RISK_WARNING}</WarningPill>
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
        <div>
          {data.procedures.map((procedure) => {
            const id = procedure.procedureId
            return (
              <details
                key={id}
                className="group border-b last:border-b-0"
                onToggle={(event) => {
                  if (event.currentTarget.open) setOpened((prev) => new Set(prev).add(id))
                }}
              >
                <summary className="flex cursor-pointer list-none items-start gap-3 py-3 text-left text-base font-medium focus-visible:ring-2 focus-visible:ring-ring sm:text-sm">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-secondary text-xs font-semibold text-success-foreground">
                    {procedureNumber(id)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      {procedure.name}
                      {MOCK_DEADLINE_TAGS[id] && (
                        <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-md bg-danger px-2 py-0.5 text-xs font-medium text-danger-foreground">
                          <TriangleAlert className="size-3" aria-hidden />
                          {MOCK_DEADLINE_TAGS[id]} (일반 기준)
                        </span>
                      )}
                      <RecheckBadge procedureId={id} />
                    </span>
                    <span className="mt-0.5 block font-normal text-muted-foreground">
                      {procedure.summary}
                    </span>
                  </span>
                  <ChevronDown
                    className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
                    aria-hidden
                  />
                </summary>
                {opened.has(id) && <StepDetail procedureId={id} />}
              </details>
            )
          })}
        </div>
      )}
      <div className="flex flex-col-reverse gap-2 pt-1 sm:flex-row sm:justify-end">
        <Button asChild variant="outline">
          <Link
            to="/checklist"
            onClick={(event) => {
              if (hasAnswers || serverPending) return
              event.preventDefault()
              event.stopPropagation()
              open("start")
            }}
          >
            <ListChecks className="size-4" aria-hidden />
            체크리스트에서 내 상황 보기
          </Link>
        </Button>
        <Button type="button" onClick={close}>
          닫기
        </Button>
      </div>
    </div>
  )
}
