// @vitest-environment jsdom
// '안내 확인' 읽음 버튼 화면 테스트(2-5-1, 2-5-2, 2-4-3, Q71). 문구 대신 버튼 상태·개수로 보여 주는지 확인한다.
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { GUIDANCE_READ_HINT, GuidanceProgress, GuidanceReadToggle } from "./guidance-read-toggle"

beforeEach(() => useInheritanceStore.getState().reset())
afterEach(cleanup)

describe("GuidanceReadToggle", () => {
  it("상세에서는 '다 읽었어요' → 누르면 '읽음'과 읽은 개수, 다시 누르면 해제된다", () => {
    render(<GuidanceReadToggle procedureId="p04" variant="detail" />)
    const button = screen.getByRole("button", { name: "다 읽었어요" })
    expect(button.getAttribute("aria-pressed")).toBe("false")
    expect(screen.getByRole("status").textContent).toBe("0/8 읽음")

    fireEvent.click(button)
    expect(screen.getByRole("button", { name: /읽음/ }).getAttribute("aria-pressed")).toBe("true")
    expect(screen.getByRole("status").textContent).toBe("1/8 읽음")
    expect(useInheritanceStore.getState().procedureStates.p04.guidanceRead).toBe(true)

    fireEvent.click(screen.getByRole("button", { name: /읽음/ }))
    expect(screen.getByRole("button", { name: "다 읽었어요" })).toBeTruthy()
    expect(useInheritanceStore.getState().procedureStates.p04.guidanceRead).toBe(false)
  })

  it("마우스를 올리면 '신청 완료가 아님' 짧은 설명이 뜨고, 화면낭독기도 같은 설명을 읽는다", () => {
    render(<GuidanceReadToggle procedureId="p04" />)
    // #227: 체크리스트 버튼 이름은 늘 "읽음"이고, 읽기 전에는 눌리지 않은 상태(aria-pressed=false)다.
    const button = screen.getByRole("button", { name: /^읽음/ })
    expect(button.getAttribute("aria-pressed")).toBe("false")
    expect(button.getAttribute("title")).toBe(GUIDANCE_READ_HINT)
    const hintId = button.getAttribute("aria-describedby") ?? ""
    expect(document.getElementById(hintId)?.textContent).toBe(GUIDANCE_READ_HINT)
  })

  it("답변이 바뀌어 재확인이 필요하면 '다시 확인하기'로 보이고, 누르면 읽음이 된다 (2-4-3)", () => {
    useInheritanceStore.getState().setGuidanceRead("p04", true)
    useInheritanceStore.setState((s) => ({
      procedureStates: {
        ...s.procedureStates,
        p04: { ...s.procedureStates.p04, needsRecheck: true },
      },
    }))
    render(<GuidanceReadToggle procedureId="p04" variant="detail" />)

    fireEvent.click(screen.getByRole("button", { name: "다시 확인하기" }))

    expect(screen.getByRole("button", { name: /읽음/ }).getAttribute("aria-pressed")).toBe("true")
    expect(useInheritanceStore.getState().procedureStates.p04.needsRecheck).toBe(false)
  })
})

describe("GuidanceProgress", () => {
  it("읽은 개수를 'N/8 읽음'과 진행 막대로 보이고, 재확인이 있으면 개수를 함께 보인다", () => {
    useInheritanceStore.getState().setGuidanceRead("p01", true)
    useInheritanceStore.getState().setGuidanceRead("p02", true)
    useInheritanceStore.setState((s) => ({
      procedureStates: {
        ...s.procedureStates,
        p03: { ...s.procedureStates.p03, needsRecheck: true },
      },
    }))
    render(<GuidanceProgress />)

    expect(screen.getByText("2/8 읽음")).toBeTruthy()
    expect(screen.getByText(/재확인 1/)).toBeTruthy()
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("2")
  })
})
