/*
 * 담당: [A] | 책임: W-02 선택 위험 질문 3개(R1~R3)와 답한 직후 안내.
 * PRD: 스토리 1-2·2-4 / 태스크 2-4-1, 2-4-3, 2-4-4. 화면정의서 v1.4 Q82 A, 15장 ① A안.
 * 구현: 각 질문은 독립 선택(있음/없음/모름)이며 '답하지 않음'으로 되돌릴 수 있다.
 *   승인된 안내 문구가 있는 답만 그 문구를, 없으면 공통 위험 경고만 보여준다.
 *   미확인 답(답변 수정·저장 후 재방문)은 [그대로 맞음]을 눌러야 확인 상태가 된다.
 * 제한사항: 새 안내 문장을 만들지 않는다. 답으로 법적 효과를 판정하지 않는다.
 */
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { COMMON_RISK_WARNING, findRiskGuidance, RISK_QUESTIONS } from "@/mocks/checklist"
import { findProcedureName } from "@/mocks/procedures"
import type { AnswerChoice } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"

const CHOICES: AnswerChoice[] = ["yes", "no", "unknown"]

export function RiskQuestions() {
  const riskAnswers = useInheritanceStore((s) => s.riskAnswers)
  const answerRisk = useInheritanceStore((s) => s.answerRisk)
  const clearRisk = useInheritanceStore((s) => s.clearRisk)
  const confirmRisk = useInheritanceStore((s) => s.confirmRisk)

  return (
    <section aria-labelledby="risk-heading" className="space-y-3">
      <div>
        <h2 id="risk-heading" className="text-lg font-semibold">
          확인이 필요한 상황 (선택 질문 3개)
        </h2>
        <p className="text-sm text-muted-foreground">
          답하지 않아도 됩니다. 답하면 관련 주의 안내를 바로 보여 드립니다.
        </p>
      </div>
      <ul className="space-y-3">
        {RISK_QUESTIONS.map((question) => {
          const current = riskAnswers[question.riskId]
          const guidance = current ? findRiskGuidance(question.riskId, current.answer) : null
          return (
            <li key={question.riskId} className="space-y-3 rounded-xl border bg-card p-4">
              <fieldset className="space-y-2">
                <legend className="font-medium">{question.question}</legend>
                <div className="flex flex-wrap gap-2">
                  {CHOICES.map((choice) => (
                    <label
                      key={choice}
                      className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm has-[:checked]:border-primary has-[:checked]:bg-muted"
                    >
                      <input
                        type="radio"
                        name={`risk-${question.riskId}`}
                        checked={current?.answer === choice}
                        onChange={() => answerRisk(question.riskId, choice)}
                      />
                      {question.answerLabels[choice]}
                    </label>
                  ))}
                  {current && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => clearRisk(question.riskId)}
                    >
                      답하지 않음
                    </Button>
                  )}
                </div>
              </fieldset>
              {current && !current.confirmed && (
                <div className="flex flex-wrap items-center gap-2 rounded-lg bg-warning px-3 py-2 text-sm text-warning-foreground">
                  <span>미확인 답변입니다. 지금도 맞는지 확인해 주세요.</span>
                  <Button type="button" size="sm" onClick={() => confirmRisk(question.riskId)}>
                    그대로 맞음
                  </Button>
                </div>
              )}
              {current?.confirmed && (
                <div
                  role="status"
                  className="space-y-2 rounded-lg bg-muted px-3 py-2 text-sm leading-6"
                >
                  {guidance && <p className="font-medium">{guidance}</p>}
                  <p>{COMMON_RISK_WARNING}</p>
                  <p className="flex flex-wrap gap-x-3">
                    관련 절차:
                    {question.relatedProcedureIds.map((id) => (
                      <Link
                        key={id}
                        to={`/procedures/${id}`}
                        className="underline underline-offset-4"
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
