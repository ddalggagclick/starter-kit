/*
 * 담당: [A] | 책임: W-02 웹 체크리스트(공통 8개 절차 카드·안내 확인·선택 위험 질문·카카오 진입).
 * PRD: 스토리 1-4, 2-1, 2-2, 2-4, 2-5 / 태스크 1-4-3, 1-4-4, 2-1-1, 2-2-1, 2-5-1, 2-5-2.
 * 구현: ?handoff= 로 들어오면 토큰을 교환해 W-01을 건너뛴다(K1 띠). 실패하면 사유를 구분하지 않는
 *   같은 안내와 '이어 보기' 또는 'W-01 처음부터'를 보여준다. 8개 카드는 항상 같은 순서로 모두 보인다.
 *   체크리스트 저장 동의 띠(ChecklistConsentBand)를 보여 주고, 저장 기록을 불러오면 그 사실을 알린다(4-1-1, D-09).
 *   저장 중이면 [체크리스트 삭제]·[체크리스트 저장 동의 철회]를 보인다(4-3).
 * 제한사항: '안내 확인' 개수를 신고·신청 완료율로 표현하지 않는다.
 */
import { ChevronRight, Pencil } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Notice } from "@/components/ui/notice"
import { useHandoff } from "@/features/kakao/use-handoff"
import { procedureNumber, useProcedureList } from "@/features/procedures/api"
import {
  GuidanceProgress,
  GuidanceReadToggle,
  RecheckBadge,
} from "@/features/procedures/guidance-read-toggle"
import { cn } from "@/lib/utils"
import {
  COMMON_RISK_WARNING,
  HANDOFF_FAILURE_COPY,
  LEGAL_DISCLAIMER,
  ONE_STOP_OPTIONS,
  RELATIONSHIP_OPTIONS,
  RISK_QUESTIONS,
} from "@/shared/content/checklist"
import { MOCK_DEADLINE_TAGS } from "@/shared/content/procedures"
import type { InitialAnswers, ProcedureId } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { ChecklistConsentBand } from "./checklist-consent-band"
import { ChecklistStorageControls } from "./checklist-storage-controls"
import { RiskQuestions } from "./risk-questions"
import { ServerSaveBand } from "./server-save-band"

const labelOf = <T extends string>(options: { value: T; label: string }[], value: T) =>
  options.find((option) => option.value === value)?.label ?? value

function AnswerSummary({ answers }: { answers: InitialAnswers }) {
  return (
    <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
      <div>
        <dt className="text-muted-foreground">고인과의 관계</dt>
        <dd className="font-medium">{labelOf(RELATIONSHIP_OPTIONS, answers.relationship)}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">사망일</dt>
        <dd className="font-medium">{answers.deathDateUnknown ? "모름" : answers.deathDate}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">안심상속 원스톱 서비스</dt>
        <dd className="font-medium">{labelOf(ONE_STOP_OPTIONS, answers.oneStopApplication)}</dd>
      </div>
    </dl>
  )
}

// 위험 질문에 '있음'으로 답했으면 관련 절차 카드에 주의 표시를 붙인다. 순서·노출은 바꾸지 않는다.
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

function ProcedureCards() {
  const { data, isPending, isError, refetch } = useProcedureList()
  const riskFlags = useRiskFlags()
  // 읽은 카드는 테두리를 초록으로 바꿔 한눈에 구분한다(문구 없이).
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
    <ol className="grid gap-3 md:grid-cols-2">
      {data.procedures.map((procedure) => (
        <li
          key={procedure.procedureId}
          className={cn(
            "flex flex-col gap-3 rounded-xl border bg-card p-4",
            procedureStates[procedure.procedureId].guidanceRead &&
              !procedureStates[procedure.procedureId].needsRecheck &&
              "border-success-foreground",
          )}
        >
          <div className="flex items-start gap-3">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary text-sm font-semibold">
              {procedureNumber(procedure.procedureId)}
            </span>
            <div className="min-w-0 space-y-1">
              <h3 className="font-semibold">{procedure.name}</h3>
              <p className="text-sm text-muted-foreground">{procedure.summary}</p>
              <div className="flex flex-wrap gap-1.5">
                {MOCK_DEADLINE_TAGS[procedure.procedureId] && (
                  <span className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground">
                    {MOCK_DEADLINE_TAGS[procedure.procedureId]} (일반 기준)
                  </span>
                )}
                {riskFlags.has(procedure.procedureId) && (
                  <span className="rounded-full bg-danger px-2 py-0.5 text-xs font-semibold text-danger-foreground">
                    위험 답변 관련 · 먼저 확인
                  </span>
                )}
                <RecheckBadge procedureId={procedure.procedureId} />
              </div>
            </div>
          </div>
          <div className="mt-auto flex items-center justify-between gap-2 border-t pt-3">
            <GuidanceReadToggle procedureId={procedure.procedureId} />
            <Link
              to={`/procedures/${procedure.procedureId}`}
              className="inline-flex items-center gap-1 text-sm font-medium underline-offset-4 hover:underline"
            >
              상세 보기
              <ChevronRight className="size-4" aria-hidden />
            </Link>
          </div>
        </li>
      ))}
    </ol>
  )
}

export function ChecklistPage() {
  const handoff = useHandoff()
  const answers = useInheritanceStore((s) => s.answers)
  const entrySource = useInheritanceStore((s) => s.entrySource)
  const [failureDismissed, setFailureDismissed] = useState(false)

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
    return (
      <div className="mx-auto max-w-xl space-y-4">
        <h1 className="text-2xl font-bold">체크리스트</h1>
        <p className="text-muted-foreground">
          먼저 질문 3개에 답하면 공통 절차 8개를 보여 드립니다.
        </p>
        <Button asChild>
          <Link to="/start">질문에 답하기</Link>
        </Button>
        {/* 삭제·철회 직후 이 화면으로 바뀌어도 결과 안내가 보이고, 답이 없어도 동의를 철회할 수 있다. */}
        <ChecklistStorageControls />
        {/* 서버 쪽도 같다: 이 기기 기록을 지운 뒤에도 서버 철회·실패 재시도를 할 수 있고(검증 ②),
            새 기기에서 로그인하면 답이 없어도 서버 기록을 불러올 수 있다(4-6-3, 리뷰 반영). */}
        <ServerSaveBand />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-semibold text-muted-foreground">W-02 · 체크리스트</p>
        <h1 className="text-2xl font-bold">지금 확인할 공통 절차</h1>
      </div>

      <Notice tone="warning">
        {COMMON_RISK_WARNING} {LEGAL_DISCLAIMER}.
      </Notice>

      {entrySource === "kakao" && (
        <Notice tone="success">
          카카오톡에서 답한 내용을 불러왔습니다. 같은 질문을 다시 묻지 않습니다.
        </Notice>
      )}

      {entrySource === "restored" && (
        <Notice tone="info">
          이 기기에 저장한 답변을 불러왔습니다. 위험 질문 답변은 [그대로 맞음]을 누르기 전까지
          반영하지 않습니다.
        </Notice>
      )}

      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">내 답변</CardTitle>
          <Button asChild variant="outline" size="sm">
            <Link to="/start">
              <Pencil className="size-4" />
              답변 수정
            </Link>
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <AnswerSummary answers={answers} />
          <ChecklistConsentBand />
          <ChecklistStorageControls />
          <ServerSaveBand />
        </CardContent>
      </Card>

      <RiskQuestions />

      <section aria-labelledby="procedures-heading" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 id="procedures-heading" className="text-lg font-semibold">
              공통 절차 8가지
            </h2>
          </div>
          {/* 문장 대신 "N/8 읽음" 진행 막대. "신청 완료 아님"은 읽음 버튼의 마우스 설명으로 알린다. */}
          <GuidanceProgress />
        </div>
        <ProcedureCards />
      </section>

      <div className="flex flex-wrap gap-3 text-sm">
        <Link to="/procedures" className="underline underline-offset-4">
          전체 절차 탐색
        </Link>
        <Link to="/guide/relationship" className="underline underline-offset-4">
          상속 관계 알아보기
        </Link>
        <Link to="/guide/tax" className="underline underline-offset-4">
          상속세 기본 안내
        </Link>
        <Link to="/ai" className="underline underline-offset-4">
          AI에게 질문하기
        </Link>
      </div>
    </div>
  )
}
