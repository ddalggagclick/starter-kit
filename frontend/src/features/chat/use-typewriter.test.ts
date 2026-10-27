// @vitest-environment jsdom
// 자동 타이핑(3-4-3)과 출처 번호 [n](A08 #184): [n]은 한 덩어리로 한 번에 나오고, 끝나면 원문과 같다.
import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { typingUnits, useTypewriter } from "./use-typewriter"

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

const ANSWER = "상속포기는 가정법원에 신고합니다[1]. 기간은 조문을 따릅니다[2][3]."

describe("typingUnits", () => {
  it("[숫자]는 한 단위, 나머지는 한 글자씩이고 이어 붙이면 원문과 같다", () => {
    const units = typingUnits(ANSWER)
    expect(units).toContain("[1]")
    expect(units).toContain("[3]")
    expect(units.join("")).toBe(ANSWER)
  })

  it("숫자가 아닌 대괄호와 이모지 같은 글자도 그대로 한 글자씩 다룬다", () => {
    expect(typingUnits("[참고] 👍")).toEqual(["[", "참", "고", "]", " ", "👍"])
  })
})

describe("useTypewriter", () => {
  it("타이핑 중간에도 '[' 또는 '[1'처럼 끊긴 출처 번호가 보이지 않고, 끝나면 원문 전체가 보인다", () => {
    const { result } = renderHook(() => useTypewriter(ANSWER))
    const seen: string[] = []
    for (let tick = 0; tick < 200 && !result.current.done; tick += 1) {
      act(() => vi.advanceTimersByTime(16))
      seen.push(result.current.shown)
    }

    expect(result.current.done).toBe(true)
    expect(result.current.shown).toBe(ANSWER)
    // 보인 텍스트 끝이 "[" 또는 "[숫자"로 끝나는 순간이 없어야 한다.
    expect(seen.filter((shown) => /\[\d*$/.test(shown))).toEqual([])
  })
})
