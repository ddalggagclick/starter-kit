/*
 * 담당: [A] | 책임: W-02 웹 체크리스트(공통 8개 절차·안내 확인·선택 위험 질문·카카오 진입).
 * PRD: 스토리 1-4, 2-1, 2-2, 2-4, 2-5 / 태스크 1-4-3, 1-4-4, 2-1-1, 2-2-1, 2-5-1, 2-5-2.
 * 구현: ?handoff= 로 들어오면 토큰을 교환해 W-01을 건너뛴다(K1 띠). 실패하면 사유를 구분하지 않는
 *   같은 안내와 '이어 보기' 또는 'W-01 처음부터'를 보여준다. 8개 절차는 항상 같은 순서로 모두 보인다.
 *   체크리스트 저장 동의 띠(ChecklistConsentBand)를 보여 주고, 저장 기록을 불러오면 그 사실을 알린다(4-1-1, D-09).
 *   저장 중이면 [체크리스트 삭제]·[체크리스트 저장 동의 철회]를 보인다(4-3).
 *   #227 새 시안(https://claude.ai/artifact/NgrnTfYvGvuGj5PYWnJcfu, 모양만 변경): 카드·테두리를 줄이고 목록 하나 + 구분선으로.
 *   - 절차 항목은 어디를 눌러도 상세로 간다(제목 링크를 항목 전체로 넓힘). 읽음 버튼은 그 위에 있어 누르면 상태만 바뀐다.
 *   - 좁은 화면은 오른쪽 체크 아이콘(44px), 넓은 화면은 기존 [읽기 전/읽음] 버튼으로 읽음을 표시한다.
 *   - [답변 수정]·[처음 시작하기]는 질문 3개를 지금 화면 위 모달로 연다(기존 /start 주소도 그대로).
 *   - 아래쪽 바로가기 링크 4개(전체 절차·상속 관계·상속세·AI)는 시안에 없어 뺐다. 같은 곳은 사이드바·첫 화면으로 간다.
 *   - 최신 시안(사용자 지시 2026-10-29): 저장은 상태 칸 + [저장](철회는 그 모달 안), [체크리스트 삭제]는 목록 아래 작은 링크.
 *     확인창·결과 안내·재시도는 전과 같다(useChecklistStorageActions). 답 이름표·안내 문장은 시안 문구를 쓴다.
 *   - 입장 순서(사용자 요청 2026-10-29): 답하기 전에 들어오면 질문 3개 모달이 먼저 뜬다. 빈 화면("먼저 상황을 알려주세요")은
 *     이 화면에서 [체크리스트 삭제]를 한 직후에만 그대로 보인다. 카카오 링크 처리 중·실패, 저장 기록을 읽는 중,
 *     서버에서 불러올 기록이 있을 때(불러오기 선택을 보여야 함)는 모달을 띄우지 않는다.
 * 제한사항: '안내 확인' 개수를 신고·신청 완료율로 표현하지 않는다.
 */
import { ArrowRight, Check, ChevronRight, SquarePen, Trash2, TriangleAlert } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice, WarningPill } from "@/components/ui/notice"
import { selectNamespace, useAuthStore } from "@/features/auth/auth-store"
import { useHandoff } from "@/features/kakao/use-handoff"
import { procedureNumber, useProcedureList } from "@/features/procedures/api"
import {
  GUIDANCE_READ_HINT,
  GuidanceProgress,
  GuidanceReadToggle,
  RecheckBadge,
} from "@/features/procedures/guidance-read-toggle"
import { cn } from "@/lib/utils"
import {
  COMMON_RISK_WARNING,
  DELETE_BUTTON_LABELS,
  HANDOFF_FAILURE_COPY,
  LEGAL_DISCLAIMER,
  ONE_STOP_OPTIONS,
  RELATIONSHIP_LABELS,
  RISK_QUESTIONS,
} from "@/shared/content/checklist"
import { MOCK_DEADLINE_TAGS } from "@/shared/content/procedures"
import type { InitialAnswers, ProcedureId } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { useOverlayStore } from "@/shared/state/overlay-store"
import { ChecklistConsentBand } from "./checklist-consent-band"
import { useChecklistStorageStore } from "./checklist-storage"
import { useChecklistStorageActions } from "./checklist-storage-controls"
import { RiskQuestions } from "./risk-questions"
import { useServerChecklistStore } from "./server-checklist"
import { ServerSaveBand } from "./server-save-band"

// 시안 제목 크기(모바일 24px, 640px 이상 28px)
const PAGE_TITLE = "text-2xl font-bold leading-snug sm:text-[1.75rem]"
// 시안 구역 제목(모바일 20px, 640px 이상 23px)
export const SECTION_TITLE = "text-xl font-semibold leading-tight sm:text-[23px]"

const labelOf = <T extends string>(options: { value: T; label: string }[], value: T) =>
  options.find((option) => option.value === value)?.label ?? value

// 내 답변: 칸을 나누지 않고 한 줄에 이어 쓴다(좁으면 줄바꿈).
function AnswerSummary({ answers }: { answers: InitialAnswers }) {
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-base">
      <div className="flex gap-2">
        <dt className="text-muted-foreground">고인과의 관계</dt>
        <dd className="font-medium">{RELATIONSHIP_LABELS[answers.relationship]}</dd>
      </div>
      <div className="flex gap-2">
        <dt className="text-muted-foreground">사망일</dt>
        <dd className="font-medium">
          {answers.deathDateUnknown || !answers.deathDate ? "모름" : answers.deathDate}
        </dd>
      </div>
      <div className="flex gap-2">
        <dt className="text-muted-foreground">원스톱 서비스</dt>
        <dd className="font-medium">{labelOf(ONE_STOP_OPTIONS, answers.oneStopApplication)}</dd>
      </div>
    </dl>
  )
}

// 위험 질문에 '있음'으로 답했으면 관련 절차에 주의 표시를 붙인다. 순서·노출은 바꾸지 않는다.
// 미확인 답(저장 후 재방문·답변 수정 영향)은 [그대로 맞음] 전까지 반영하지 않는다(D-09, Q70).
const useRiskFlags = (): Set<ProcedureId> => {
  const riskAnswers = useInheritanceStore((s) => s.riskAnswers)
  const flagged = new Set<ProcedureId>()
  for (const question of RISK_QUESTIONS) {
    const answer = riskAnswers[question.riskId]
    if (answer?.confirmed && answer.answer === "yes") {
      for (const id of question.relatedProcedureIds) flagged.add(id)
    }
  }
  return flagged
}

// 좁은 화면용 읽음 표시: 오른쪽 위 체크 아이콘(누르는 영역 44px). 동작은 [읽기 전/읽음] 버튼과 같다.
function MobileReadCheck({ procedureId, name }: { procedureId: ProcedureId; name: string }) {
  const state = useInheritanceStore((s) => s.procedureStates[procedureId])
  const setGuidanceRead = useInheritanceStore((s) => s.setGuidanceRead)
  const read = state.guidanceRead && !state.needsRecheck
  return (
    <button
      type="button"
      aria-pressed={read}
      aria-label={`${name} 읽음 표시`}
      title={GUIDANCE_READ_HINT}
      onClick={() => setGuidanceRead(procedureId, !read)}
      className="relative z-10 -mt-2 -mr-2 grid size-11 shrink-0 place-items-center rounded-full sm:hidden"
    >
      <span
        aria-hidden
        className={cn(
          "grid size-6 place-items-center rounded-full border-2 transition-colors",
          read
            ? "border-success-foreground bg-success-foreground text-card"
            : "border-input bg-card text-input",
        )}
      >
        <Check className="size-3.5" />
      </span>
    </button>
  )
}

function ProcedureList() {
  const { data, isPending, isError, refetch } = useProcedureList()
  const riskFlags = useRiskFlags()
  const procedureStates = useInheritanceStore((s) => s.procedureStates)
  if (isPending) return <p role="status">절차를 불러오는 중…</p>
  if (isError)
    return (
      <Notice tone="danger">
        절차를 불러오지 못했습니다.{" "}
        <button type="button" className="underline" onClick={() => refetch()}>
          다시 시도
        </button>
      </Notice>
    )
  return (
    <ol className="divide-y rounded-xl border bg-card">
      {data.procedures.map((procedure) => {
        const id = procedure.procedureId
        const read = procedureStates[id].guidanceRead && !procedureStates[id].needsRecheck
        return (
          <li
            key={id}
            className="relative flex items-start gap-3 px-4 py-3.5 transition-colors hover:bg-muted sm:items-center sm:gap-4 sm:px-5"
          >
            {/* 번호 동그라미: 읽으면 초록 ✓로 바뀐다(문구 없이 한눈에). */}
            <span
              aria-hidden
              className={cn(
                "grid size-7 shrink-0 place-items-center rounded-full text-sm font-semibold",
                read ? "bg-success-foreground text-card" : "bg-secondary text-success-foreground",
              )}
            >
              {read ? "✓" : procedureNumber(id)}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                {/* 제목 링크를 항목 전체로 넓혀(after:absolute) 어디를 눌러도 상세로 간다. */}
                <Link
                  to={`/procedures/${id}`}
                  className="text-[17px] font-semibold leading-7 outline-none after:absolute after:inset-0 after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
                >
                  {procedure.name}
                </Link>
                {MOCK_DEADLINE_TAGS[id] && (
                  <span className="inline-flex items-center gap-1 rounded-md bg-danger px-2 py-0.5 text-xs font-medium text-danger-foreground">
                    <TriangleAlert className="size-3" aria-hidden />
                    {MOCK_DEADLINE_TAGS[id]} (일반 기준)
                  </span>
                )}
                {riskFlags.has(id) && (
                  <span className="rounded-full bg-danger-foreground px-2 py-0.5 text-xs font-semibold text-white">
                    위험 답변 관련 · 먼저 확인
                  </span>
                )}
                <RecheckBadge procedureId={id} />
              </div>
              <p className="mt-1 text-sm leading-normal text-muted-foreground sm:mt-0.5 sm:text-[13px]">
                {procedure.summary}
              </p>
            </div>
            <MobileReadCheck procedureId={id} name={procedure.name} />
            <div className="relative z-10 hidden shrink-0 sm:block">
              <GuidanceReadToggle procedureId={id} />
            </div>
            <ChevronRight
              className="hidden size-5 shrink-0 text-muted-foreground sm:block"
              aria-hidden
            />
          </li>
        )
      })}
    </ol>
  )
}

export function ChecklistPage() {
  const handoff = useHandoff()
  const answers = useInheritanceStore((s) => s.answers)
  const entrySource = useInheritanceStore((s) => s.entrySource)
  const openOverlay = useOverlayStore((s) => s.open)
  // 계정이 바뀌면 답한 화면을 새로 그려 이전 계정의 확인창·결과 안내를 버린다.
  const namespace = useAuthStore(selectNamespace)
  const [failureDismissed, setFailureDismissed] = useState(false)
  const storageStatus = useChecklistStorageStore((s) => s.status)
  const lastAction = useChecklistStorageStore((s) => s.lastAction)
  const serverPending = useServerChecklistStore((s) => s.pending !== null)
  const deletedHere =
    lastAction?.action === "delete" && lastAction.ok && lastAction.namespace === namespace
  // 이 화면에서 답을 본 적이 있으면(예: [체크리스트 삭제]로 지워짐) 모달 없이 빈 화면을 보인다. 모달은 한 번만 연다.
  const sawAnswers = useRef(answers !== null)
  const prompted = useRef(false)
  useEffect(() => {
    if (answers !== null) sawAnswers.current = true
  }, [answers])
  useEffect(() => {
    if (prompted.current || sawAnswers.current || answers !== null) return
    if (handoff !== "none" || storageStatus === "checking" || serverPending || deletedHere) return
    prompted.current = true
    openOverlay("start")
  }, [answers, handoff, storageStatus, serverPending, deletedHere, openOverlay])

  if (handoff === "exchanging") {
    return <p role="status">카카오톡에서 답한 내용을 불러오는 중…</p>
  }

  if (handoff === "failed" && !failureDismissed) {
    return (
      <div className="mx-auto max-w-xl space-y-4">
        <Notice tone="danger">
          <p className="font-semibold">{HANDOFF_FAILURE_COPY}</p>
          <p>
            링크가 만료되었거나 이미 사용되었을 수 있습니다. 카카오톡에서 다시 링크를 받거나
            아래에서 이어가세요.
          </p>
        </Notice>
        <div className="flex flex-wrap gap-3">
          {answers ? (
            <Button type="button" onClick={() => setFailureDismissed(true)}>
              이 기기의 이전 답변으로 이어 보기
            </Button>
          ) : (
            <Button asChild>
              <Link to="/start">질문 3개에 처음부터 답하기</Link>
            </Button>
          )}
        </div>
      </div>
    )
  }

  if (!answers) {
    // 시안 빈 상태: 가운데 안내 칸 + [처음 시작하기](질문 3개 모달).
    return (
      <div className="mx-auto max-w-xl space-y-4">
        <h1 className={PAGE_TITLE}>먼저 상황을 알려주세요</h1>
        <p className="text-base text-muted-foreground">
          처음 시작에서 질문에 답하면 맞춤 체크리스트가 열려요.
        </p>
        <div className="flex flex-col items-center gap-2 rounded-xl border bg-card px-6 py-10 text-center">
          <strong className="text-lg">아직 상황을 알려주지 않았어요</strong>
          <span className="text-base text-muted-foreground">
            세 가지 질문에 답하면 맞춤 체크리스트가 열려요.
          </span>
          <Button
            type="button"
            aria-haspopup="dialog"
            className="mt-2 h-11"
            onClick={() => openOverlay("start")}
          >
            처음 시작하기
            <ArrowRight className="size-4" aria-hidden />
          </Button>
        </div>
        {/* 삭제·철회 직후 이 화면으로 바뀌어도 결과 안내가 보이고, 답이 없어도 [저장]에서 동의를 철회할 수 있다. */}
        <ChecklistStorageArea />
        {/* 서버 쪽도 같다: 이 기기 기록을 지운 뒤에도 서버 철회·실패 재시도를 할 수 있고(검증 ②),
            새 기기에서 로그인하면 답이 없어도 서버 기록을 불러올 수 있다(4-6-3, 리뷰 반영). */}
        <ServerSaveBand />
      </div>
    )
  }

  return <AnsweredChecklist key={namespace} answers={answers} entrySource={entrySource} />
}

// 답이 없는 화면의 저장 칸: 상태 + [저장](철회) + 결과 안내
function ChecklistStorageArea() {
  const storage = useChecklistStorageActions()
  return (
    <>
      <ChecklistConsentBand onRevoke={() => storage.request("revoke")} />
      {storage.view}
    </>
  )
}

function AnsweredChecklist({
  answers,
  entrySource,
}: {
  answers: InitialAnswers
  entrySource: ReturnType<typeof useInheritanceStore.getState>["entrySource"]
}) {
  const openOverlay = useOverlayStore((s) => s.open)
  const storage = useChecklistStorageActions()
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className={PAGE_TITLE}>지금 확인할 공통 절차</h1>
        <WarningPill>
          {COMMON_RISK_WARNING} {LEGAL_DISCLAIMER}.
        </WarningPill>
        {entrySource === "kakao" && (
          <Notice tone="success">
            카카오톡에서 답한 내용을 불러왔습니다. 같은 질문을 다시 묻지 않습니다.
          </Notice>
        )}
        {entrySource === "restored" && (
          <p role="status" className="text-base text-muted-foreground">
            이 기기에 저장한 답변을 불러왔습니다. 확인이 필요한 상황의 답은 [확인]을 누르기 전까지
            반영하지 않습니다.
          </p>
        )}
      </header>

      {/* 내 답변: 카드 대신 위아래 선 하나로 묶는다. 저장 동의·삭제·서버 저장은 전과 같다. */}
      <section aria-labelledby="answers-heading" className="space-y-3 border-y py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="answers-heading" className="text-base font-semibold">
            내 답변
          </h2>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9"
            aria-haspopup="dialog"
            onClick={() => openOverlay("start")}
          >
            <SquarePen className="size-4" aria-hidden />
            답변 수정
          </Button>
        </div>
        <AnswerSummary answers={answers} />
        <ChecklistConsentBand onRevoke={() => storage.request("revoke")} />
        {storage.view}
        <ServerSaveBand />
      </section>

      <RiskQuestions />

      <section aria-labelledby="procedures-heading" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="procedures-heading" className={SECTION_TITLE}>
            상속 공통 절차
          </h2>
          {/* 문장 대신 "N/8 읽음" 진행 막대. "신청 완료 아님"은 읽음 버튼의 마우스 설명으로 알린다. */}
          <GuidanceProgress />
        </div>
        <ProcedureList />
        {/* 체크리스트 삭제: 목록 바로 아래, 눈에 덜 띄게(저장 중일 때만) */}
        {storage.available && (
          <div className="flex justify-end">
            <button
              type="button"
              disabled={storage.busy}
              onClick={() => storage.request("delete")}
              className="inline-flex items-center gap-1.5 px-1 text-sm text-muted-foreground underline-offset-4 hover:text-danger-foreground hover:underline"
            >
              <Trash2 className="size-3.5" aria-hidden />
              {DELETE_BUTTON_LABELS.checklist}
            </button>
          </div>
        )}
      </section>
    </div>
  )
}
