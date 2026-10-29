/*
 * 담당: [A] | 책임: W-02 선택 위험 질문 3개(R1~R3)와 답한 직후 안내.
 * PRD: 스토리 1-2·2-4 / 태스크 2-4-1, 2-4-3, 2-4-4. 화면정의서 v1.4 Q82 A, 15장 ① A안.
 * 구현: 각 질문은 독립 선택(있음/없음/모름)이며 '답하지 않음'으로 되돌릴 수 있다.
 *   승인된 안내 문구가 있는 답만 그 문구를, 없으면 공통 위험 경고만 보여준다.
 *   미확인 답(답변 수정·저장 후 재방문)은 [확인]을 눌러야 확인 상태가 된다(최신 시안 문구, 2026-10-29).
 *   #227 새 시안(모양만 변경): 질문 3개를 한 목록 + 구분선으로 묶고, 오른쪽 위에 상태(미답변·미확인·확인됨)를
 *   기호와 색으로 보인다. 선택지는 둥근 버튼 모양이지만 그대로 라디오 버튼이다(키보드·화면낭독기 동작 같음).
 *   답한 뒤 안내는 들여쓰기 + 왼쪽 선 + 옅은 바탕으로 질문과 구분한다.
 * 제한사항: 새 안내 문장을 만들지 않는다. 답으로 법적 효과를 판정하지 않는다.
 */
import { Check, CircleHelp, Circle as CircleIcon, TriangleAlert } from "lucide-react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { COMMON_RISK_WARNING, findRiskGuidance, RISK_QUESTIONS } from "@/shared/content/checklist"
import { findProcedureName } from "@/shared/content/procedures"
import type { AnswerChoice } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"

const CHOICES: AnswerChoice[] = ["yes", "no", "unknown"]

// 둥근 선택 버튼 모양(시안). 실제 입력은 화면에서만 감춘 라디오 버튼이다. 질문 3개(W-01)도 같은 모양을 쓴다.
export const CHOICE_CLASS =
  "inline-flex h-9 cursor-pointer max-md:min-h-11 items-center rounded-full border border-input bg-card px-3.5 text-sm font-medium transition-colors hover:bg-muted has-[:checked]:border-primary has-[:checked]:bg-secondary has-[:checked]:font-semibold has-[:checked]:text-primary has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring"

type RiskAnswerState = { answer: AnswerChoice; confirmed: boolean } | undefined

// 오른쪽 위 상태 표시: 미답변(점선) · 미확인(노랑) · 확인됨(초록)
function RiskStatus({ current }: { current: RiskAnswerState }) {
  if (!current)
    return (
      <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-dashed px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
        <CircleIcon className="size-3" aria-hidden />
        미답변
      </span>
    )
  if (!current.confirmed)
    return (
      <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-warning px-2.5 py-0.5 text-xs font-semibold text-warning-foreground">
        <CircleHelp className="size-3" aria-hidden />
        미확인
      </span>
    )
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-success px-2.5 py-0.5 text-xs font-semibold text-success-foreground">
      <Check className="size-3" aria-hidden />
      확인됨
    </span>
  )
}

export function RiskQuestions() {
  const riskAnswers = useInheritanceStore((s) => s.riskAnswers)
  const answerRisk = useInheritanceStore((s) => s.answerRisk)
  const clearRisk = useInheritanceStore((s) => s.clearRisk)
  const confirmRisk = useInheritanceStore((s) => s.confirmRisk)

  return (
    <section aria-labelledby="risk-heading" className="space-y-3">
      <div>
        <h2 id="risk-heading" className="text-xl font-semibold leading-tight sm:text-[23px]">
          확인이 필요한 상황 (선택 질문 3개)
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          답하지 않아도 됩니다. 답하면 관련 주의 안내를 바로 보여 드립니다.
        </p>
      </div>
      <ul className="divide-y rounded-xl border bg-card">
        {RISK_QUESTIONS.map((question, index) => {
          const current = riskAnswers[question.riskId]
          const guidance = current ? findRiskGuidance(question.riskId, current.answer) : null
          return (
            <li key={question.riskId} className="space-y-3 p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3">
                <p className="text-xs font-semibold text-muted-foreground">질문 {index + 1}</p>
                <RiskStatus current={current} />
              </div>
              <fieldset className="space-y-3">
                <legend className="text-[17px] font-semibold leading-snug">
                  {question.question}
                </legend>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="mr-1 text-sm text-muted-foreground">내 선택</span>
                  {CHOICES.map((choice) => (
                    <label key={choice} className={CHOICE_CLASS}>
                      <input
                        type="radio"
                        className="sr-only"
                        name={`risk-${question.riskId}`}
                        checked={current?.answer === choice}
                        onChange={() => answerRisk(question.riskId, choice)}
                      />
                      {question.answerLabels[choice]}
                    </label>
                  ))}
                  {current && (
                    <button
                      type="button"
                      onClick={() => clearRisk(question.riskId)}
                      className="px-2 text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
                    >
                      답하지 않음
                    </button>
                  )}
                </div>
              </fieldset>
              {current && !current.confirmed && (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-warning-foreground/20 bg-warning px-3 py-2 text-sm text-warning-foreground">
                  <span>저장해 둔 선택을 불러왔어요. 지금도 맞으면 [확인]을 눌러 주세요.</span>
                  <Button
                    type="button"
                    size="sm"
                    className="px-4"
                    onClick={() => confirmRisk(question.riskId)}
                  >
                    확인
                  </Button>
                </div>
              )}
              {current?.confirmed && (
                <div
                  role="status"
                  className="ml-2 space-y-1.5 rounded-r-lg border-l-2 border-primary/40 bg-muted px-4 py-3 text-base leading-7"
                >
                  <p className="text-xs font-semibold text-muted-foreground">답변</p>
                  {guidance && (
                    <p className="flex items-start gap-1.5 font-semibold text-danger-foreground">
                      <TriangleAlert className="mt-1.5 size-4 shrink-0" aria-hidden />
                      {guidance}
                    </p>
                  )}
                  <p>{COMMON_RISK_WARNING}</p>
                  <p className="flex flex-wrap gap-x-3 text-sm">
                    관련 절차:
                    {question.relatedProcedureIds.map((id) => (
                      <Link
                        key={id}
                        to={`/procedures/${id}`}
                        className="underline underline-offset-4 hover:text-primary"
                      >
                        {findProcedureName(id)}
                      </Link>
                    ))}
                  </p>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
