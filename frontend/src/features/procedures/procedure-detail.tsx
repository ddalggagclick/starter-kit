/*
 * 담당: [A] | 책임: W-04 절차 상세 화면.
 * PRD: E2 / 스토리 2-3 / 태스크 2-3-1, 2-3-2.
 * 구현: 바로 할 행동·기한·위험·담당 기관은 접을 수 없게 항상 펼친다. 서류·방법·예외·문의는
 *   <details> 접기형(키보드 Enter/Space로 열고 닫음). 4건 이상이면 처음에 접는다(원고 1장, 명세서 8-4절).
 *   공식 출처 링크와 "공식 링크에서 직접 확인" 문구는 항상 보인다.
 *   #227 새 시안(https://claude.ai/artifact/NgrnTfYvGvuGj5PYWnJcfu, 모양만 변경): 핵심 칸 4개를 빨간 계열로 —
 *   기한·위험은 빨간 바탕, 바로 할 행동·담당 기관은 흰 바탕 + 빨간 아이콘·왼쪽 선(위험도 차이 유지).
 *   접기 칸은 오른쪽 화살표로 같은 모양. 맨 위 돌아가기는 답한 뒤면 [체크리스트로], 아니면 [전체 절차로](모달).
 *   제목 위에 "N/8", 아래에 기한 표시·한 줄 요약을 보인다.
 *   최신 시안(사용자 지시 2026-10-29): 필요 서류·신청 방법은 처음부터 펼치고 예외·참고·문의처는 접는다(건수 규칙 대신).
 *   '함께 보면 좋은 절차'는 시안에 없어 뺐다. 검수 상태 문구는 맨 아래 한 줄로 둔다.
 *   UI 전면 개편 지시서 5·6장: 핵심 4칸(행동·기한·위험·기관)을 아이보리 바탕 한 묶음("핵심 확인 정보")으로 합치고
 *   칸 사이는 얇은 선으로만 나눈다(카드 안 카드 없음). 기한·위험만 빨간 제목, 행동·기관은 네이비 제목.
 *   "기한 · 채무는 공식 자료로 확인하세요."는 묶음 제목 옆(모바일은 아래 줄)에 둔다. 묶음과 자세한 안내 사이에 구분선.
 *   자세한 안내 순서: 신청 방법·필요 서류(펼침) → 예외·참고·문의처(접힘). 제목을 먼저 읽게 위쪽 보조 정보
 *   (돌아가기·"공식 절차 상세 N/8")는 작게 한 줄로, [체크리스트로 돌아가기]는 맨 아래 [읽음] 옆에도 둔다.
 *   핵심 확인 정보 4칸: 웹은 칸마다 흰 카드, 모바일은 선으로 나눈 한 묶음(절차 1 미리보기 → 전체 적용, 2026-10-30).
 *   기한 칩은 제목 바로 오른쪽, 아래쪽 정렬(추가 수정 지시서 4장). 내부 검수 상태 문구는 사용자 지시로 뺐다.
 *   상세 화면 안의 [정보 오류 제보]는 사용자 지시로 뺐다(바닥글의 공통 [정보 오류 제보]는 그대로).
 * 근거 콘텐츠: W-04 공식 안내 원고 p01~p08 (김현주, 2026-10-22) → mocks/procedures.ts.
 * 완료 기준: 접기 상태와 관계없이 행동·기한·위험·기관이 보인다.
 * 제한사항: 출처 없는 사실을 추가하지 않는다. 재방문 접힘 상태(M-10)는 미결정이다.
 */
import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  ExternalLink,
  House,
  type LucideIcon,
  TriangleAlert,
} from "lucide-react"
import { Link, useParams } from "react-router"
import { Notice, WarningPill } from "@/components/ui/notice"
import { cn } from "@/lib/utils"
import type { ProcedureDetailWire } from "@/shared/api/types"
import { COMMON_RISK_WARNING } from "@/shared/content/checklist"
import {
  CHECK_OFFICIAL_SOURCE,
  findProcedureName,
  MOCK_DEADLINE_TAGS,
  OFFICIAL_LINK_GAP_NOTES,
} from "@/shared/content/procedures"
import type { ProcedureId } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { useOverlayStore } from "@/shared/state/overlay-store"
import { procedureNumber, useProcedureDetail, useProcedureList } from "./api"
import { GuidanceReadToggle, RecheckBadge } from "./guidance-read-toggle"

// strong: 실제 위험(기한·위험)만 빨간 제목·아이콘. 나머지는 네이비 제목.
const ALWAYS_OPEN: {
  key: "action" | "deadline" | "risk" | "agency"
  label: string
  icon: LucideIcon
  strong: boolean
}[] = [
  { key: "action", label: "바로 할 행동", icon: ArrowRight, strong: false },
  { key: "deadline", label: "기한", icon: TriangleAlert, strong: true },
  { key: "risk", label: "위험 · 주의", icon: TriangleAlert, strong: true },
  { key: "agency", label: "담당 기관", icon: House, strong: false },
]

// open: 처음부터 펼침(시안). 재방문 때 접힘 상태 유지 여부(M-10)는 미결정이라 정하지 않는다.
const OPTIONAL: {
  key: "documents" | "methods" | "exceptions" | "contacts"
  label: string
  open: boolean
}[] = [
  { key: "methods", label: "신청 방법", open: true },
  { key: "documents", label: "필요 서류", open: true },
  { key: "exceptions", label: "예외 · 참고", open: false },
  { key: "contacts", label: "문의처", open: false },
]

function ProcedureBody({ detail }: { detail: ProcedureDetailWire }) {
  return (
    <>
      <section
        aria-label="항상 표시되는 핵심 안내"
        className="rounded-2xl border border-primary/10 bg-emphasis px-4 py-4 sm:px-6 sm:py-5"
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <h2 id="key-info-heading" className="text-lg font-semibold text-primary">
            핵심 확인 정보
          </h2>
          <WarningPill className="max-sm:basis-full">{COMMON_RISK_WARNING}</WarningPill>
        </div>
        {/* 칸 4개. 사용자 지시(2026-10-30): 절차 1 미리보기를 확인한 뒤 8개 절차 모두에 적용 —
            웹(640px 이상)은 칸마다 흰 카드(2열), 모바일은 얇은 선으로 나눈 한 묶음. */}
        <dl className="mt-3 grid divide-y divide-border sm:grid-cols-2 sm:gap-3 sm:divide-y-0">
          {ALWAYS_OPEN.map(({ key, label, icon: Icon, strong }) => (
            <div
              key={key}
              className="py-3 sm:rounded-xl sm:border sm:bg-card sm:px-4 sm:py-4 sm:shadow-sm"
            >
              <dt
                className={cn(
                  "flex items-center gap-1.5 text-base font-semibold leading-snug",
                  strong ? "text-danger-foreground" : "text-primary",
                )}
              >
                <Icon
                  className={cn(
                    "size-[18px] shrink-0",
                    strong ? "text-danger-foreground" : "text-muted-foreground",
                  )}
                  aria-hidden
                />
                {label}
              </dt>
              {/* 본문은 모두 기본 글자색. 빨간색은 기한·위험 제목에만 써서 강조가 흐려지지 않게 한다. */}
              <dd className="mt-1 text-base leading-7 text-foreground">
                {detail[key] ?? "공식 자료에서 확인하세요."}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* 핵심 정보와 자세한 안내 사이 구분선(한 번만) */}
      <hr className="border-border" />

      <section aria-label="자세한 안내" className="space-y-2">
        {OPTIONAL.map(({ key, label, open }) => {
          const items = detail[key] ?? []
          if (items.length === 0) return null
          return (
            <details key={key} open={open} className="group rounded-xl border bg-card">
              <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-base font-semibold focus-visible:ring-2 focus-visible:ring-ring">
                {label}
                <span className="text-sm font-normal text-muted-foreground">({items.length})</span>
                <ChevronDown
                  className="ml-auto size-5 text-muted-foreground transition-transform group-open:rotate-180"
                  aria-hidden
                />
              </summary>
              <ul className="list-disc space-y-1.5 px-4 pb-4 pl-9 text-base leading-7">
                {items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </details>
          )
        })}
      </section>

      <section aria-label="공식 출처" className="space-y-2 rounded-xl border bg-card p-4">
        <h2 className="text-base font-semibold">공식 출처에서 직접 확인</h2>
        <ul className="space-y-1.5">
          {(detail.officialLinks ?? []).map((link) => (
            <li key={link.url}>
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-base underline underline-offset-4 hover:text-primary"
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
        <p className="text-sm text-muted-foreground">{CHECK_OFFICIAL_SOURCE}</p>
      </section>
    </>
  )
}

// 돌아가기: 답한 뒤면 체크리스트로, 아직이면 전체 절차 모달을 연다(시안).
// placement="top"은 위쪽 작은 링크, "bottom"은 [정보 오류 제보] 아래 버튼 모양이다.
function BackLink({ placement = "top" }: { placement?: "top" | "bottom" }) {
  const hasAnswers = useInheritanceStore((s) => s.answers !== null)
  const openOverlay = useOverlayStore((s) => s.open)
  const className =
    placement === "top"
      ? "inline-flex min-h-11 items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
      : "inline-flex min-h-11 items-center gap-1.5 rounded-md border bg-card px-4 text-base font-semibold text-primary hover:bg-accent"
  if (hasAnswers)
    return (
      <Link to="/checklist" className={className}>
        <ArrowLeft className="size-4" aria-hidden />
        {placement === "top" ? "체크리스트로" : "체크리스트로 돌아가기"}
      </Link>
    )
  return (
    <button
      type="button"
      aria-haspopup="dialog"
      className={className}
      onClick={() => openOverlay("steps")}
    >
      <ArrowLeft className="size-4" aria-hidden />
      전체 절차로
    </button>
  )
}

export function ProcedureDetailPage() {
  const { procedureId = "" } = useParams()
  const { data, isPending, isError } = useProcedureDetail(procedureId)
  // 한 줄 요약은 목록 응답(A06)에 있다. 목록을 아직 못 받았으면 요약 없이 보인다.
  const { data: list } = useProcedureList()
  const summary = list?.procedures.find((item) => item.procedureId === procedureId)?.summary

  return (
    // 블록 사이: 모바일 group 20px, 데스크톱 block 32px(황금비 간격 리듬).
    <article className="mx-auto max-w-3xl space-y-group md:space-y-block">
      {/* 보조 줄: 돌아가기(왼쪽) · 화면 이름과 순서(오른쪽, 작게). 제목과 겨루지 않게 작은 글씨. */}
      <div className="-mb-2 flex flex-wrap items-center justify-between gap-x-3">
        <BackLink />
        {data?.procedureId && (
          <p className="text-xs font-semibold text-muted-foreground">
            공식 절차 상세 · {procedureNumber(data.procedureId as ProcedureId)}/8
          </p>
        )}
      </div>
      {isPending && <p role="status">상세 안내를 불러오는 중…</p>}
      {isError && (
        <Notice tone="danger">
          찾을 수 없는 절차입니다. 전체 절차 목록에서 다시 선택해 주세요.
        </Notice>
      )}
      {data?.procedureId && (
        <>
          <header className="space-y-2">
            {/* 제목과 기한 칩을 한 줄로 묶고 칩은 제목 아래쪽에 맞춘다. 좁으면 칩이 다음 줄로 내려간다. */}
            <div className="flex flex-wrap items-end gap-x-3 gap-y-1.5">
              <h1 className="flex flex-wrap items-center gap-2 text-2xl font-bold leading-snug text-primary sm:text-[1.75rem]">
                {findProcedureName(data.procedureId)}
                <RecheckBadge procedureId={data.procedureId} />
              </h1>
              {MOCK_DEADLINE_TAGS[data.procedureId] && (
                <span className="mb-1 inline-flex items-center gap-1 rounded-md bg-danger px-2 py-0.5 text-sm font-medium text-danger-foreground">
                  <TriangleAlert className="size-3" aria-hidden />
                  {MOCK_DEADLINE_TAGS[data.procedureId]}
                </span>
              )}
            </div>
            {summary && <p className="text-base text-muted-foreground">{summary}</p>}
          </header>
          <ProcedureBody detail={data} />
          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
            <GuidanceReadToggle procedureId={data.procedureId} variant="detail" />
            <BackLink placement="bottom" />
          </div>
        </>
      )}
    </article>
  )
}
