// A17 itemStates 변환 테스트(계약 없음 — 제안 형태). 알아볼 수 없는 서버 값은 지어내지 않고 null로 둔다.
import { describe, expect, it } from "vitest"
import type { ChecklistSnapshot } from "@/shared/storage/db"
import { fromItemStates, toItemStates } from "./server-checklist-api"

const SNAPSHOT: ChecklistSnapshot = {
  answers: {
    relationship: "spouse",
    deathDate: null,
    deathDateUnknown: true,
    oneStopApplication: "no",
  },
  riskAnswers: { debt: { riskId: "debt", answer: "yes", confirmed: true } },
  procedureStates: {} as ChecklistSnapshot["procedureStates"],
}

describe("itemStates 변환", () => {
  it("체크리스트를 한 항목으로 넣고 그대로 되돌린다", () => {
    expect(fromItemStates(toItemStates(SNAPSHOT))).toEqual(SNAPSHOT)
  })

  it("답이 없으면 빈 배열이다", () => {
    expect(toItemStates(null)).toEqual([])
  })

  it("알아볼 수 없는 모양이면 null이다", () => {
    expect(fromItemStates(undefined)).toBeNull()
    expect(fromItemStates([{ foo: 1 }])).toBeNull()
    expect(fromItemStates("x")).toBeNull()
  })
})
