// @vitest-environment jsdom
// W-05·W-06 일반 안내 B1 검수 반영 확인(PRD 2-6-2, 검수 2026-10-26). 실제 라우터 + 메모리 IndexedDB.
import { splitCitation } from "./cited-text"
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, describe, expect, it } from "vitest"
import { appRoutes, createQueryClient } from "@/app"

const renderAt = (path: string) =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={createMemoryRouter(appRoutes, { initialEntries: [path] })} />
    </QueryClientProvider>,
  )

afterEach(cleanup)

const expectNoPreReviewMark = () => {
  expect(screen.queryByText(/검수 전 Mock/)).toBeNull()
  expect(screen.queryByText(/검증 필요/)).toBeNull()
}

// 근거 조문 괄호는 다음 줄(별도 요소)로 보이므로, 목록 항목 전체 글자로 원문 문장이 그대로인지 확인한다.
const sentence = (text: string) => (_: string, element: Element | null) =>
  element?.tagName === "LI" && element.textContent === text

describe("W-05 상속 관계 (검수 반영)", () => {
  it("촌수·태아 문장을 근거 조문과 함께 보이고 검수 전 표시가 없다", () => {
    renderAt("/guide/relationship")

    expect(
      screen.getByText(
        sentence(
          "같은 순위의 상속인이 여러 명이면 촌수가 가장 가까운 사람이 먼저 상속인이 되고, 촌수가 같은 사람이 여러 명이면 함께 상속인이 됩니다. (민법 제1000조 제2항)",
        ),
      ),
    ).toBeTruthy()
    expect(
      screen.getByText(
        sentence("태아는 상속 순위에서 이미 태어난 것으로 봅니다. (민법 제1000조 제3항)"),
      ),
    ).toBeTruthy()
    expectNoPreReviewMark()
  })
})

describe("W-06 상속세 (검수 반영)", () => {
  it("신고 기한 원문 표현과 국외 9개월 문장을 보이고, 세액 계산 안 함 안내는 유지한다", () => {
    renderAt("/guide/tax")

    expect(
      screen.getByText(
        sentence(
          "상속개시일이 속하는 달의 말일부터 6개월 이내에 신고합니다. (상속세 및 증여세법 제67조 제1항)",
        ),
      ),
    ).toBeTruthy()
    expect(
      screen.getByText(
        sentence(
          "피상속인이나 상속인이 외국에 주소를 둔 경우에는 9개월 이내입니다. (같은 법 제67조 제4항)",
        ),
      ),
    ).toBeTruthy()
    expect(screen.getByText(/이 서비스는 세액을 계산하지 않습니다/)).toBeTruthy()
    expect(screen.queryByText(/속한 달의 말일부터 6개월 이내로 안내됩니다/)).toBeNull()
    expectNoPreReviewMark()
  })
})

describe("근거 조문 개행 (사용자 지시 2026-10-30)", () => {
  it("문장 끝 '제N조' 괄호만 떼어 다음 줄로 보이고, 조문 없는 문장은 그대로 둔다", () => {
    expect(
      splitCitation(
        "상속개시일이 속하는 달의 말일부터 6개월 이내 (상속세 및 증여세법 제67조 제1항)",
      ),
    ).toEqual(["상속개시일이 속하는 달의 말일부터 6개월 이내", "(상속세 및 증여세법 제67조 제1항)"])
    expect(splitCitation("사망신고서(제19호 서식)")).toEqual(["사망신고서(제19호 서식)", null])
    expect(splitCitation("진단서(진단서·검안서 등)를 준비하세요.")).toEqual([
      "진단서(진단서·검안서 등)를 준비하세요.",
      null,
    ])
  })
})
