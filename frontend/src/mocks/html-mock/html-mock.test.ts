// @vitest-environment jsdom
// 클릭 Mock 스모크 테스트: 실제 브라우저 검증을 대신하지 않는다.
import { beforeAll, describe, expect, it } from "vitest"

const root = () => document.getElementById("mock-root") as HTMLElement
const screen = () => root().querySelector("#screen") as HTMLElement

const until = async (check: () => boolean, timeoutMs = 6000) => {
  const start = Date.now()
  while (!check()) {
    if (Date.now() - start > timeoutMs) throw new Error("시간 초과")
    await new Promise((resolve) => setTimeout(resolve, 20))
  }
}

const click = (selector: string) => {
  const element = root().querySelector<HTMLElement>(selector)
  if (!element) throw new Error(`없음: ${selector}`)
  element.click()
}

beforeAll(async () => {
  document.body.innerHTML = `<div id="mock-root"></div>`
  window.location.hash = "#/w-00"
  await import("./main")
})

describe("클릭 Mock 흐름", () => {
  it("모든 화면 맨 위에 공통 위험 경고가 있다", () => {
    expect(root().querySelector(".common-warning")?.textContent).toContain("기한 · 채무")
  })

  it("W-00 → W-01, 빈 제출은 인라인 오류로 이동하지 않는다", async () => {
    click('[data-to="#/w-01"].primary')
    await until(() => screen().dataset.route === "w-01")
    click('form[data-form="w01"] button[type="submit"]')
    expect(root().querySelectorAll(".field-error")).toHaveLength(3)
    expect(screen().dataset.route).toBe("w-01")
  })

  it("세 문항을 답하면 W-02로 이동하고 8개 절차가 보인다", async () => {
    click('input[name="relationship"][value="spouse"]')
    click('input[name="deathDateUnknown"]')
    click('input[name="oneStopApplication"][value="no"]')
    click('form[data-form="w01"] button[type="submit"]')
    await until(() => screen().dataset.route === "w-02")
    expect(root().querySelectorAll(".procedure-card")).toHaveLength(8)
  })

  it("W-04 상세는 행동·기한·기관을 항상 펼치고 나머지는 접는다", async () => {
    click('[data-to="#/w-04/p04"]')
    await until(() => screen().dataset.route === "w-04")
    expect(root().querySelectorAll(".always")).toHaveLength(3)
    const fold = root().querySelector<HTMLButtonElement>(".fold-head")
    expect(fold?.getAttribute("aria-expanded")).toBe("false")
    fold?.click()
    expect(root().querySelector(".fold-head")?.getAttribute("aria-expanded")).toBe("true")
  })

  it("W-07 질문 → S2 진행 → S3 검증 답변과 출처", async () => {
    window.location.hash = "#/w-07"
    await until(() => screen().dataset.route === "w-07")
    click('[data-action="example"]')
    click('form[data-form="chat"] button[type="submit"]')
    await until(() => root().textContent?.includes("공식 자료 검색 중") ?? false)
    await until(() => root().querySelector(".sources") !== null, 10000)
    expect(root().querySelectorAll(".sources li")).toHaveLength(2)
    expect(root().textContent).toContain("추가 출처 보기")
  }, 15000)

  it("저장 안 된 대화에서 다른 메뉴로 가면 S11 확인창", () => {
    click('[data-to="#/w-03"]')
    expect(root().querySelector(".modal")?.textContent).toContain("나가면 사라집니다")
    click('[data-action="close-modal"]')
    expect(root().querySelector(".modal")).toBeNull()
  })
})
