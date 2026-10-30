/*
 * 담당: [A] | 책임: W-01 웹 초기 3문항 폼과 W-02 전환, 기존 답변 수정.
 * PRD: E2 / 스토리 2-1, 2-4 / 태스크 2-1-1, 2-1-2, 2-4-1.
 * 구현: 관계(6개) · 사망일(날짜 또는 '모름') · 안심상속 신청 여부. 빈 답은 해당 칸에 오류를 보이고 이동하지 않는다.
 *   이미 답한 상태로 들어오면 수정 모드다. 저장하면 영향받은 안내만 재확인 표시된다(store).
 *   #227 새 시안(https://claude.ai/artifact/NgrnTfYvGvuGj5PYWnJcfu, 모양만 변경): 질문 3개를 한 목록 + 구분선으로,
 *   선택지는 둥근 버튼 모양(실제는 라디오·체크 상자 그대로), 위에 진행 단계 3칸을 보인다. 첫 화면·체크리스트에서는
 *   지금 화면 위 모달로 열린다(/start 주소로 오면 전처럼 페이지로 보인다).
 *   모달 안에서는 다 답하거나 [취소]를 누르면 모달만 닫히고, 다른 화면에서 열었으면 체크리스트로 간다(전과 같은 흐름).
 *   최신 시안(사용자 지시 2026-10-29): 제목·부제·선택지 문구는 시안 그대로, 공통 위험 경고는 모달 뒤 화면에 있어 두지 않는다.
 *   관계와 안심상속을 고르기 전에는 [체크리스트 보기]가 눌리지 않고 옆에 이유를 한 줄로 보인다. 사망일은 비워도 된다.
 * 제한사항: 답변으로 상속인 자격·기한을 판정하지 않는다.
 */
import { ArrowRight, CircleHelp, Info } from "lucide-react"
import { useId } from "react"
import { useLocation, useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import { cn } from "@/lib/utils"
import {
  INITIAL_QUESTION_COPY,
  ONE_STOP_OPTIONS,
  RELATIONSHIP_OPTIONS,
} from "@/shared/content/checklist"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { useInOverlay, useOverlayStore } from "@/shared/state/overlay-store"
import { CHOICE_CLASS } from "./risk-questions"
import { toInitialAnswers, useInitialForm } from "./use-initial-form"

// 진행 단계 3칸(시안). 지금은 1단계(상황 확인)다.
const STEPS = [
  { title: "상황 확인", body: "관계·사망일·신청 여부" },
  { title: "기한 확인", body: "중요한 날짜 먼저 보기" },
  { title: "체크하며 진행", body: "할 일을 하나씩" },
] as const

// 질문 제목: 번호는 색으로 구분하고, 화면낭독기에는 "1. 고인과…"처럼 읽힌다. htmlFor가 있으면 입력칸 이름(label)이 된다.
function QuestionTitle({
  id,
  htmlFor,
  number,
  children,
}: {
  id?: string
  htmlFor?: string
  number: number
  children: string
}) {
  const Tag = htmlFor ? "label" : "p"
  return (
    <Tag id={id} htmlFor={htmlFor} className="mb-3 block text-base font-semibold sm:text-[15px]">
      <span className="mr-1.5 text-primary tabular-nums">{number}</span>
      <span className="sr-only">. </span>
      {children}
    </Tag>
  )
}

export function InitialQuestionsPage() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const inOverlay = useInOverlay()
  const closeOverlay = useOverlayStore((s) => s.close)
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
  // 시안: 관계와 안심상속 여부를 골라야 [체크리스트 보기]가 눌린다.
  const ready = Boolean(watch("relationship")) && Boolean(watch("oneStopApplication"))
  const ids = { relationship: useId(), deathDate: useId(), oneStop: useId() }

  // 체크리스트 화면 위 모달이면 모달만 닫는다(같은 화면이라 이동할 곳이 없다). 그 밖에는 체크리스트로 간다.
  const goToChecklist = () => {
    if (inOverlay && pathname === "/checklist") closeOverlay()
    else navigate("/checklist")
  }

  const onValid = handleSubmit((values) => {
    setInitialAnswers(toInitialAnswers(values), entrySource ?? "direct")
    goToChecklist()
  })

  const errorCount = Object.keys(errors).length

  return (
    <div className={cn("space-y-group", !inOverlay && "mx-auto max-w-2xl")}>
      <div className="space-y-2 pr-8">
        <h1 className="text-lg font-semibold leading-none">{INITIAL_QUESTION_COPY.title}</h1>
        <p className="text-sm text-muted-foreground">{INITIAL_QUESTION_COPY.description}</p>
      </div>

      <ol aria-label="진행 단계" className="grid gap-3 sm:grid-cols-3">
        {STEPS.map((step, index) => {
          const current = index === 0
          return (
            <li
              key={step.title}
              aria-current={current ? "step" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-xl border bg-card px-3.5 py-3 text-sm text-muted-foreground",
                current && "border-primary/40 text-foreground",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "grid size-[26px] shrink-0 place-items-center rounded-full border text-xs font-bold",
                  current ? "border-primary bg-primary text-primary-foreground" : "bg-muted",
                )}
              >
                {index + 1}
              </span>
              <span>
                <strong className="block text-sm font-semibold text-foreground">
                  {step.title}
                </strong>
                {step.body}
              </span>
            </li>
          )
        })}
      </ol>

      {isSubmitted && errorCount > 0 && (
        <Notice tone="danger">
          답하지 않은 질문이 {errorCount}개 있습니다. 표시된 칸을 확인해 주세요.
        </Notice>
      )}

      <form onSubmit={onValid} noValidate className="space-y-4">
        <div className="divide-y rounded-xl border bg-card px-4 sm:px-5">
          <div className="py-4">
            <QuestionTitle id={`${ids.relationship}-label`} number={1}>
              {INITIAL_QUESTION_COPY.relationship}
            </QuestionTitle>
            <fieldset
              aria-labelledby={`${ids.relationship}-label`}
              aria-describedby={errors.relationship ? ids.relationship : undefined}
              className="flex flex-wrap gap-1.5"
            >
              {RELATIONSHIP_OPTIONS.map((option) => (
                <label key={option.value} className={CHOICE_CLASS}>
                  <input
                    type="radio"
                    className="sr-only"
                    value={option.value}
                    {...register("relationship")}
                  />
                  {option.label}
                </label>
              ))}
            </fieldset>
            {errors.relationship && (
              <p id={ids.relationship} className="mt-2 text-sm text-danger-foreground">
                {errors.relationship.message}
              </p>
            )}
          </div>

          <div className="py-4">
            <QuestionTitle htmlFor={`${ids.deathDate}-input`} number={2}>
              {INITIAL_QUESTION_COPY.deathDate}
            </QuestionTitle>
            <div className="flex flex-wrap items-center gap-2.5">
              <input
                id={`${ids.deathDate}-input`}
                type="date"
                disabled={deathDateUnknown}
                aria-invalid={Boolean(errors.deathDate)}
                aria-describedby={errors.deathDate ? ids.deathDate : undefined}
                className="h-11 w-full max-w-[220px] rounded-md border border-input bg-card px-3 text-base shadow-xs disabled:bg-muted disabled:text-muted-foreground sm:h-[42px] sm:text-sm"
                {...register("deathDate")}
              />
              {/* '모름'은 체크 상자 그대로, 모양만 둥근 버튼이다. */}
              <label className={cn(CHOICE_CLASS, "gap-1.5")}>
                <input type="checkbox" className="sr-only" {...register("deathDateUnknown")} />
                <CircleHelp className="size-3.5" aria-hidden />
                {INITIAL_QUESTION_COPY.deathDateUnknownLabel}
              </label>
            </div>
            <p className="mt-2.5 flex items-start gap-1.5 text-sm text-muted-foreground">
              <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              {INITIAL_QUESTION_COPY.deathDateNote}
            </p>
            {errors.deathDate && (
              <p id={ids.deathDate} className="mt-2 text-sm text-danger-foreground">
                {errors.deathDate.message}
              </p>
            )}
          </div>

          <div className="py-4">
            <QuestionTitle id={`${ids.oneStop}-label`} number={3}>
              {INITIAL_QUESTION_COPY.oneStopApplication}
            </QuestionTitle>
            <fieldset
              aria-labelledby={`${ids.oneStop}-label`}
              aria-describedby={errors.oneStopApplication ? ids.oneStop : undefined}
              className="flex flex-wrap gap-1.5"
            >
              {ONE_STOP_OPTIONS.map((option) => (
                <label key={option.value} className={CHOICE_CLASS}>
                  <input
                    type="radio"
                    className="sr-only"
                    value={option.value}
                    {...register("oneStopApplication")}
                  />
                  {option.label}
                </label>
              ))}
            </fieldset>
            {errors.oneStopApplication && (
              <p id={ids.oneStop} className="mt-2 text-sm text-danger-foreground">
                {errors.oneStopApplication.message}
              </p>
            )}
          </div>
        </div>

        {/* 아래쪽 줄: 안내 한 줄 + [체크리스트 보기]. [모두 건너뛰고 보기]는 빈 화면으로 가서 뺐다(사용자 결정). 수정 중 [취소]는 페이지(/start)에서만. */}
        <div className="flex w-full flex-wrap items-center justify-end gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span role="status" className="text-sm text-muted-foreground">
              {ready ? INITIAL_QUESTION_COPY.readyHint : INITIAL_QUESTION_COPY.notReadyHint}
            </span>
            {editing && !inOverlay && (
              <Button
                type="button"
                variant="outline"
                className="h-11"
                onClick={() => navigate("/checklist")}
              >
                취소
              </Button>
            )}
            <Button type="submit" className="h-11 px-5" disabled={!ready}>
              {editing ? "수정 내용 반영" : INITIAL_QUESTION_COPY.submitButton}
              <ArrowRight className="size-4" aria-hidden />
            </Button>
          </div>
        </div>
      </form>
    </div>
  )
}
