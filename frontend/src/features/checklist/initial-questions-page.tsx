/*
 * 담당: [A] | 책임: W-01 웹 초기 3문항 폼과 W-02 전환, 기존 답변 수정.
 * PRD: E2 / 스토리 2-1, 2-4 / 태스크 2-1-1, 2-1-2, 2-4-1.
 * 구현: 관계(6개) · 사망일(날짜 또는 '모름') · 안심상속 신청 여부. 빈 답은 해당 칸에 오류를 보이고 이동하지 않는다.
 *   이미 답한 상태로 들어오면 수정 모드다. 저장하면 영향받은 안내만 재확인 표시된다(store).
 * 제한사항: 답변으로 상속인 자격·기한을 판정하지 않는다.
 */
import { useId } from "react"
import { useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Notice } from "@/components/ui/notice"
import {
  COMMON_RISK_WARNING,
  INITIAL_QUESTION_COPY,
  ONE_STOP_OPTIONS,
  RELATIONSHIP_OPTIONS,
} from "@/mocks/checklist"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { toInitialAnswers, useInitialForm } from "./use-initial-form"

const optionClass =
  "flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2.5 text-sm has-[:checked]:border-primary has-[:checked]:bg-muted has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring"

export function InitialQuestionsPage() {
  const navigate = useNavigate()
  const answers = useInheritanceStore((state) => state.answers)
  const entrySource = useInheritanceStore((state) => state.entrySource)
  const setInitialAnswers = useInheritanceStore((state) => state.setInitialAnswers)
  const editing = answers !== null
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitted },
  } = useInitialForm(answers)
  const deathDateUnknown = watch("deathDateUnknown")
  const ids = { relationship: useId(), deathDate: useId(), oneStop: useId() }

  const onValid = handleSubmit((values) => {
    setInitialAnswers(toInitialAnswers(values), entrySource ?? "direct")
    navigate("/checklist")
  })

  const errorCount = Object.keys(errors).length

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-semibold text-muted-foreground">W-01 · 질문 3개</p>
        <h1 className="text-2xl font-bold">{editing ? "답변 수정" : "몇 가지만 알려 주세요"}</h1>
        <p className="text-muted-foreground">
          답변은 안내를 고르는 데만 쓰이며 법률 판단을 대신하지 않습니다.
        </p>
      </div>
      <Notice tone="warning">{COMMON_RISK_WARNING}</Notice>
      {isSubmitted && errorCount > 0 && (
        <Notice tone="danger">
          답하지 않은 질문이 {errorCount}개 있습니다. 표시된 칸을 확인해 주세요.
        </Notice>
      )}
      <form onSubmit={onValid} noValidate className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle className="text-base" id={`${ids.relationship}-label`}>
              1. {INITIAL_QUESTION_COPY.relationship}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <fieldset
              aria-labelledby={`${ids.relationship}-label`}
              aria-describedby={errors.relationship ? ids.relationship : undefined}
              className="grid gap-2 sm:grid-cols-3"
            >
              {RELATIONSHIP_OPTIONS.map((option) => (
                <label key={option.value} className={optionClass}>
                  <input type="radio" value={option.value} {...register("relationship")} />
                  {option.label}
                </label>
              ))}
            </fieldset>
            {errors.relationship && (
              <p id={ids.relationship} className="mt-2 text-sm text-danger-foreground">
                {errors.relationship.message}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              <label htmlFor={`${ids.deathDate}-input`}>2. {INITIAL_QUESTION_COPY.deathDate}</label>
            </CardTitle>
            <CardDescription>
              날짜를 모르면 '모름'을 선택하세요. 모름도 답변으로 저장됩니다.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <input
              id={`${ids.deathDate}-input`}
              type="date"
              disabled={deathDateUnknown}
              aria-invalid={Boolean(errors.deathDate)}
              aria-describedby={errors.deathDate ? ids.deathDate : undefined}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50 sm:w-60"
              {...register("deathDate")}
            />
            <label className="flex w-fit cursor-pointer items-center gap-2 text-sm">
              <input type="checkbox" {...register("deathDateUnknown")} />
              {INITIAL_QUESTION_COPY.deathDateUnknownLabel}
            </label>
            {errors.deathDate && (
              <p id={ids.deathDate} className="text-sm text-danger-foreground">
                {errors.deathDate.message}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base" id={`${ids.oneStop}-label`}>
              3. {INITIAL_QUESTION_COPY.oneStopApplication}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <fieldset
              aria-labelledby={`${ids.oneStop}-label`}
              aria-describedby={errors.oneStopApplication ? ids.oneStop : undefined}
              className="grid gap-2 sm:grid-cols-3"
            >
              {ONE_STOP_OPTIONS.map((option) => (
                <label key={option.value} className={optionClass}>
                  <input type="radio" value={option.value} {...register("oneStopApplication")} />
                  {option.label}
                </label>
              ))}
            </fieldset>
            {errors.oneStopApplication && (
              <p id={ids.oneStop} className="mt-2 text-sm text-danger-foreground">
                {errors.oneStopApplication.message}
              </p>
            )}
          </CardContent>
        </Card>

        <div className="flex flex-wrap gap-3">
          <Button type="submit" size="lg">
            {editing ? "수정 내용 반영" : INITIAL_QUESTION_COPY.submitButton}
          </Button>
          {editing && (
            <Button
              type="button"
              size="lg"
              variant="outline"
              onClick={() => navigate("/checklist")}
            >
              취소
            </Button>
          )}
        </div>
      </form>
    </div>
  )
}
