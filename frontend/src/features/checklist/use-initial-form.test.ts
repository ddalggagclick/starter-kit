// W-01 입력 검사 단위 테스트: 미선택과 사망일 '모름' 구분, 오류는 해당 칸에만.
import { describe, expect, it } from "vitest"
import {
  INITIAL_FORM_ERRORS,
  type InitialFormValues,
  initialFormSchema,
  toInitialAnswers,
} from "./use-initial-form"

const errorsOf = (values: InitialFormValues) => {
  const result = initialFormSchema.safeParse(values)
  if (result.success) return {}
  return Object.fromEntries(result.error.issues.map((issue) => [issue.path[0], issue.message]))
}

describe("initialFormSchema", () => {
  it("아무것도 고르지 않으면 세 칸 모두 각자의 오류", () => {
    expect(
      errorsOf({
        relationship: "",
        deathDate: "",
        deathDateUnknown: false,
        oneStopApplication: "",
      }),
    ).toEqual({
      relationship: INITIAL_FORM_ERRORS.relationship,
      deathDate: INITIAL_FORM_ERRORS.deathDateMissing,
      oneStopApplication: INITIAL_FORM_ERRORS.oneStopApplication,
    })
  })

  it("사망일 '모름'은 답변으로 통과하고 날짜는 null로 바뀐다", () => {
    const values = {
      relationship: "unknown",
      deathDate: "",
      deathDateUnknown: true,
      oneStopApplication: "unknown",
    }
    expect(errorsOf(values)).toEqual({})
    expect(toInitialAnswers(values)).toEqual({
      relationship: "unknown",
      deathDate: null,
      deathDateUnknown: true,
      oneStopApplication: "unknown",
    })
  })

  it("미래 날짜는 거부한다", () => {
    expect(
      errorsOf({
        relationship: "spouse",
        deathDate: "2999-01-01",
        deathDateUnknown: false,
        oneStopApplication: "yes",
      }),
    ).toEqual({ deathDate: INITIAL_FORM_ERRORS.deathDateInvalid })
  })
})
