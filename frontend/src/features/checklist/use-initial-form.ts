/*
 * 담당: [A] | 책임: W-01 초기 3문항 입력과 W-02 전환.
 * PRD: E2 / 스토리 2-1, 2-4 / 태스크 2-1-1, 2-1-2, 2-4-1.
 * 구현: react-hook-form + zod로 관계·사망일(날짜 또는 '모름')·안심상속 신청 여부를 검사한다.
 * 완료 기준: 미선택과 사망일 '모름'을 구분하고, 오류는 해당 칸에 표시하며 선택을 임의로 바꾸지 않는다.
 * 제한사항: 초기 답변을 법률 판정으로 해석하지 않는다. 서버 재검증(2-1-3)은 B1 책임이다.
 */
import { zodResolver } from "@hookform/resolvers/zod"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import type { AnswerChoice, InitialAnswers, Relationship } from "@/shared/contracts/domain"

const RELATIONSHIPS: readonly Relationship[] = [
  "spouse",
  "descendant",
  "ascendant",
  "sibling",
  "other",
  "unknown",
]
const CHOICES: readonly AnswerChoice[] = ["yes", "no", "unknown"]

// 선택하지 않은 값은 빈 문자열로 둔다. '모름'(unknown)과 섞지 않는다.
export type InitialFormValues = {
  relationship: string
  deathDate: string
  deathDateUnknown: boolean
  oneStopApplication: string
}

export const INITIAL_FORM_ERRORS = {
  relationship: "고인과의 관계를 선택해 주세요.",
  deathDateMissing: "사망일을 입력하거나 '모름'을 선택해 주세요.",
  deathDateInvalid: "올바른 날짜를 입력해 주세요. 오늘 이후 날짜는 입력할 수 없습니다.",
  oneStopApplication: "안심상속 원스톱 서비스 신청 여부를 선택해 주세요.",
} as const

const todayIso = () => {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const isValidPastDate = (value: string) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00`)
  return !Number.isNaN(parsed.getTime()) && value <= todayIso()
}

export const initialFormSchema = z
  .object({
    relationship: z.string(),
    deathDate: z.string(),
    deathDateUnknown: z.boolean(),
    oneStopApplication: z.string(),
  })
  .superRefine((values, ctx) => {
    if (!(RELATIONSHIPS as readonly string[]).includes(values.relationship)) {
      ctx.addIssue({
        code: "custom",
        path: ["relationship"],
        message: INITIAL_FORM_ERRORS.relationship,
      })
    }
    if (!values.deathDateUnknown) {
      if (!values.deathDate) {
        ctx.addIssue({
          code: "custom",
          path: ["deathDate"],
          message: INITIAL_FORM_ERRORS.deathDateMissing,
        })
      } else if (!isValidPastDate(values.deathDate)) {
        ctx.addIssue({
          code: "custom",
          path: ["deathDate"],
          message: INITIAL_FORM_ERRORS.deathDateInvalid,
        })
      }
    }
    if (!(CHOICES as readonly string[]).includes(values.oneStopApplication)) {
      ctx.addIssue({
        code: "custom",
        path: ["oneStopApplication"],
        message: INITIAL_FORM_ERRORS.oneStopApplication,
      })
    }
  })

// 검사를 통과한 값만 넘긴다. '모름'이면 날짜는 null, deathDateUnknown은 true(A04·A05 규칙과 같음).
export const toInitialAnswers = (values: InitialFormValues): InitialAnswers => ({
  relationship: values.relationship as Relationship,
  deathDate: values.deathDateUnknown ? null : values.deathDate,
  deathDateUnknown: values.deathDateUnknown,
  oneStopApplication: values.oneStopApplication as AnswerChoice,
})

export const toFormValues = (answers: InitialAnswers | null): InitialFormValues => ({
  relationship: answers?.relationship ?? "",
  deathDate: answers?.deathDate ?? "",
  deathDateUnknown: answers?.deathDateUnknown ?? false,
  oneStopApplication: answers?.oneStopApplication ?? "",
})

// 저장소의 답이 바뀌면 폼을 그 값으로 다시 채운다. 로그아웃·계정 전환으로 답이 비면 폼도 비워
// 이전 계정의 답이 입력창에 남지 않게 한다(4-2-2). 사용자가 입력 중인 값은 저장소 답이 바뀔 때만 덮인다.
export const useInitialForm = (answers: InitialAnswers | null) => {
  const form = useForm<InitialFormValues>({
    resolver: zodResolver(initialFormSchema),
    defaultValues: toFormValues(answers),
  })
  const { reset } = form
  useEffect(() => {
    reset(toFormValues(answers))
  }, [answers, reset])
  return form
}
