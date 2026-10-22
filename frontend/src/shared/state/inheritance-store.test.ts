// 체크리스트 메모리 상태 단위 테스트: 답변 수정 → 영향받은 위험 질문만 미확인, 확인한 영향 절차만 재확인.
import { beforeEach, describe, expect, it } from "vitest"
import type { InitialAnswers } from "@/shared/contracts/domain"
import { countGuidance, useInheritanceStore } from "./inheritance-store"

const BASE: InitialAnswers = {
  relationship: "descendant",
  deathDate: "2026-09-30",
  deathDateUnknown: false,
  oneStopApplication: "unknown",
}

const store = () => useInheritanceStore.getState()

describe("inheritance-store", () => {
  beforeEach(() => store().reset())

  it("처음 답하면 재확인 없이 답만 저장한다", () => {
    store().setInitialAnswers(BASE, "direct")
    expect(store().answers).toEqual(BASE)
    expect(countGuidance(store().procedureStates)).toEqual({ read: 0, recheck: 0, total: 8 })
  })

  it("사망일을 바꾸면 이미 확인한 영향 절차만 재확인, 확인 안 한 절차는 그대로", () => {
    store().setInitialAnswers(BASE, "direct")
    store().setGuidanceRead("p04", true) // 영향 받음 + 확인함
    store().setGuidanceRead("p02", true) // 영향 없음
    store().answerRisk("self_application", "yes")
    store().answerRisk("debt", "no")

    store().setInitialAnswers({ ...BASE, deathDate: null, deathDateUnknown: true }, "direct")

    const states = store().procedureStates
    expect(states.p04).toEqual({ guidanceRead: true, needsRecheck: true })
    expect(states.p01).toEqual({ guidanceRead: false, needsRecheck: false })
    expect(states.p02).toEqual({ guidanceRead: true, needsRecheck: false })
    // 사망일과 연결된 위험 질문만 미확인, 답 자체는 유지
    expect(store().riskAnswers.self_application).toEqual({
      riskId: "self_application",
      answer: "yes",
      confirmed: false,
    })
    expect(store().riskAnswers.debt?.confirmed).toBe(true)
    expect(countGuidance(states)).toEqual({ read: 1, recheck: 1, total: 8 })
  })

  it("[그대로 맞음]을 눌러야 확인 상태가 된다", () => {
    store().setInitialAnswers(BASE, "direct")
    store().answerRisk("self_application", "yes")
    store().setInitialAnswers({ ...BASE, deathDate: "2026-09-01" }, "direct")
    expect(store().riskAnswers.self_application?.confirmed).toBe(false)
    store().confirmRisk("self_application")
    expect(store().riskAnswers.self_application?.confirmed).toBe(true)
  })

  it("위험 답을 바꾸면 그 위험과 관련된 확인 절차만 재확인한다", () => {
    store().setInitialAnswers(BASE, "direct")
    store().answerRisk("debt", "no")
    store().setGuidanceRead("p03", true)
    store().setGuidanceRead("p08", true)
    store().answerRisk("debt", "yes")
    expect(store().procedureStates.p03.needsRecheck).toBe(true)
    expect(store().procedureStates.p08.needsRecheck).toBe(false)
  })

  it("다시 확인하면 재확인 배지가 사라지고 확인 수에 들어간다", () => {
    store().setInitialAnswers(BASE, "direct")
    store().setGuidanceRead("p02", true)
    store().setInitialAnswers({ ...BASE, relationship: "spouse" }, "direct")
    expect(store().procedureStates.p02.needsRecheck).toBe(true)
    store().setGuidanceRead("p02", true)
    expect(store().procedureStates.p02).toEqual({ guidanceRead: true, needsRecheck: false })
  })

  it("'답하지 않음'은 '모름'과 다르게 키를 지운다", () => {
    store().answerRisk("debt", "unknown")
    expect(store().riskAnswers.debt?.answer).toBe("unknown")
    store().clearRisk("debt")
    expect(store().riskAnswers.debt).toBeUndefined()
  })

  it("Handoff 결과를 카카오 진입으로 반영하고 위험 답은 확인 상태로 받는다", () => {
    store().applyHandoff({ ...BASE, risks: [{ riskId: "property_disposal", answer: "yes" }] })
    expect(store().entrySource).toBe("kakao")
    expect(store().answers).toEqual(BASE)
    expect(store().riskAnswers.property_disposal?.confirmed).toBe(true)
  })
})
