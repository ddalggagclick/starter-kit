// @vitest-environment jsdom
// W-01 입력 검사 단위 테스트: 미선택과 사망일 '모름' 구분, 오류는 해당 칸에만.
import { renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { InitialAnswers } from "@/shared/contracts/domain"
import {
  INITIAL_FORM_ERRORS,
  type InitialFormValues,
  initialFormSchema,
  toInitialAnswers,
  useInitialForm,
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

describe("useInitialForm 계정 전환 (리뷰 회귀)", () => {
  const A: InitialAnswers = {
    relationship: "spouse",
    deathDate: "2026-09-30",
    deathDateUnknown: false,
    oneStopApplication: "yes",
  }

  it("저장소 답이 비면(로그아웃·계정 전환) 이전 계정 답을 입력창에서 지운다", () => {
    const { result, rerender } = renderHook(
      ({ answers }: { answers: InitialAnswers | null }) => useInitialForm(answers),
      { initialProps: { answers: A as InitialAnswers | null } },
    )
    expect(result.current.getValues("relationship")).toBe("spouse")

    rerender({ answers: null })

    expect(result.current.getValues()).toEqual({
      relationship: "",
      deathDate: "",
      deathDateUnknown: false,
      oneStopApplication: "",
    })
  })

  it("새 계정 기록이 복원되면 그 답으로 다시 채운다", () => {
    const { result, rerender } = renderHook(
      ({ answers }: { answers: InitialAnswers | null }) => useInitialForm(answers),
      { initialProps: { answers: null as InitialAnswers | null } },
    )

    rerender({ answers: { ...A, relationship: "sibling" } })

    expect(result.current.getValues("relationship")).toBe("sibling")
  })
})
