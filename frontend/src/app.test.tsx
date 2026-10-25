// @vitest-environment jsdom
// V1 화면 흐름 스모크 테스트(jsdom + Mock 데이터). 실제 브라우저·Backend 검증을 대신하지 않는다.
import { QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { useAuthStore } from "@/features/auth/auth-store"
import { useChatSessionStore } from "@/features/chat/chat-store"
import { MOCK_ACCOUNT, MOCK_VALID_HANDOFF_TOKEN, resetMockApiState } from "@/mocks/mock-api"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { appRoutes, createQueryClient } from "./app"

const renderAt = (path: string) => {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return router
}

beforeEach(() => {
  resetMockApiState()
  useInheritanceStore.getState().reset()
  useAuthStore.getState().signOut()
  useChatSessionStore.setState({ externalNoticeAcknowledged: false, guestRemaining: 10 })
})
afterEach(cleanup)

describe("W-01 → W-02", () => {
  it("빈 답으로 제출하면 칸마다 오류를 보이고 이동하지 않는다", async () => {
    const router = renderAt("/start")
    fireEvent.click(screen.getByRole("button", { name: "체크리스트 확인" }))
    expect(await screen.findByText("고인과의 관계를 선택해 주세요.")).toBeTruthy()
    expect(screen.getByText("사망일을 입력하거나 '모름'을 선택해 주세요.")).toBeTruthy()
    expect(screen.getByText("안심상속 원스톱 서비스 신청 여부를 선택해 주세요.")).toBeTruthy()
    expect(router.state.location.pathname).toBe("/start")
  })

  it("세 답을 고르면 W-02에 공통 절차 8개와 공통 위험 경고가 보인다", async () => {
    const router = renderAt("/start")
    fireEvent.click(screen.getByLabelText("배우자"))
    fireEvent.click(screen.getByLabelText("모름", { selector: "input[type=checkbox]" }))
    fireEvent.click(screen.getByLabelText("신청 안 함"))
    fireEvent.click(screen.getByRole("button", { name: "체크리스트 확인" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/checklist"))
    await screen.findByText("부동산 상속", {}, { timeout: 2000 })
    expect(screen.getAllByRole("link", { name: /상세 보기/ })).toHaveLength(8)
    expect(screen.getAllByText(/기한 · 채무는 공식 자료로 확인하세요/).length).toBeGreaterThan(0)
    expect(screen.getByText("배우자")).toBeTruthy()
  })

  it("안내 확인을 체크해도 카드 순서·개수는 그대로이고 확인 수만 바뀐다", async () => {
    useInheritanceStore.getState().setInitialAnswers(
      {
        relationship: "descendant",
        deathDate: "2026-09-30",
        deathDateUnknown: false,
        oneStopApplication: "yes",
      },
      "direct",
    )
    renderAt("/checklist")
    await screen.findByText("부동산 상속", {}, { timeout: 2000 })
    const before = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)
    fireEvent.click(screen.getAllByLabelText("안내 확인")[0])
    expect(screen.getByText(/안내 확인/, { selector: "p[aria-live]" }).textContent).toContain("1")
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(before)
  })
})

describe("카카오 Handoff (Mock)", () => {
  it("유효 토큰은 W-01 없이 W-02에 답을 넣고 주소에서 토큰을 지운다", async () => {
    const router = renderAt(`/checklist?handoff=${MOCK_VALID_HANDOFF_TOKEN}`)
    expect(router.state.location.search).toBe("")
    expect(await screen.findByText(/카카오톡에서 답한 내용을 불러왔습니다/)).toBeTruthy()
    expect(useInheritanceStore.getState().entrySource).toBe("kakao")
  })

  it("이미 쓴 토큰과 없는 토큰은 같은 실패 안내를 보인다", async () => {
    renderAt(`/checklist?handoff=${MOCK_VALID_HANDOFF_TOKEN}`)
    await screen.findByText(/카카오톡에서 답한 내용을 불러왔습니다/)
    cleanup()
    useInheritanceStore.getState().reset()
    renderAt(`/checklist?handoff=${MOCK_VALID_HANDOFF_TOKEN}`)
    const reused = (await screen.findByRole("alert")).textContent
    cleanup()
    renderAt("/checklist?handoff=unknown-token")
    const unknown = (await screen.findByRole("alert")).textContent
    expect(reused).toBe(unknown)
    expect(screen.getByRole("link", { name: "질문 3개에 처음부터 답하기" })).toBeTruthy()
  })
})

describe("W-04 상세", () => {
  it("행동·기한·위험·기관은 항상 보이고 나머지는 접기형이다", async () => {
    renderAt("/procedures/p04")
    const core = await screen.findByRole("region", { name: "항상 표시되는 핵심 안내" })
    for (const label of ["바로 할 행동", "기한", "위험 · 주의", "담당 기관"]) {
      expect(within(core).getByText(label)).toBeTruthy()
    }
    expect(core.querySelector("details")).toBeNull()
    const optional = screen.getByRole("region", { name: "자세한 안내" })
    const sections = Array.from(optional.querySelectorAll("details"))
    expect(sections.length).toBe(4)
    // 4건 이상이면 접고(서류 4건), 3건 이하면 펼친다(방법 3건) — 원고 1장, 명세서 8-4절
    expect(sections.map((d) => d.open)).toEqual([false, true, true, true])
  })

  it("공식 링크가 없는 p02는 '공식 링크에서 직접 확인'과 이유를 보인다", async () => {
    renderAt("/procedures/p02")
    const sources = await screen.findByRole("region", { name: "공식 출처" })
    expect(within(sources).queryAllByRole("link")).toHaveLength(0)
    expect(within(sources).getByText("공식 링크에서 직접 확인하세요.")).toBeTruthy()
    expect(within(sources).getByText(/연결할 공식 안내 페이지가 없습니다/)).toBeTruthy()
  })

  it("오류 제보 Mock 모달은 열고 닫히며 전송 기능이 없다", async () => {
    renderAt("/procedures/p01")
    await screen.findByRole("region", { name: "항상 표시되는 핵심 안내" })
    fireEvent.click(screen.getAllByRole("button", { name: /정보 오류 제보/ })[0])
    const dialog = screen.getByRole("dialog")
    expect(within(dialog).getByText(/전송되거나 저장되지 않습니다/)).toBeTruthy()
    expect(within(dialog).queryByRole("textbox")).toBeNull()
    fireEvent.click(within(dialog).getByRole("button", { name: "닫기" }))
    expect(screen.queryByRole("dialog")).toBeNull()
  })
})

describe("W-07 AI (Mock)", () => {
  it("외부 전송 안내를 확인하기 전에는 보낼 수 없고, 200자를 넘으면 막는다", () => {
    renderAt("/ai")
    const send = screen.getByRole("button", { name: "보내기" }) as HTMLButtonElement
    expect(send.disabled).toBe(true)
    fireEvent.click(screen.getByRole("button", { name: "확인했습니다" }))
    expect(send.disabled).toBe(false)
    fireEvent.change(screen.getByLabelText("질문"), { target: { value: "가".repeat(201) } })
    expect(screen.getByText(/201\/200자/)).toBeTruthy()
    expect(send.disabled).toBe(true)
  })

  it("예시 질문은 입력칸만 채운다", () => {
    renderAt("/ai")
    fireEvent.click(screen.getByRole("button", { name: "상속세" }))
    expect((screen.getByLabelText("질문") as HTMLTextAreaElement).value).toBe("상속세")
    // 제출 전이므로 진행 상태나 답변이 생기지 않는다.
    expect(screen.queryByText(/질문을 보내는 중|공식 자료 검색 중/)).toBeNull()
  })

  it("비로그인 10회를 다 쓰면 S9와 로그인 진입을 보여준다", async () => {
    useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 0 })
    renderAt("/ai")
    fireEvent.change(screen.getByLabelText("질문"), { target: { value: "상속포기 기한" } })
    fireEvent.click(screen.getByRole("button", { name: "보내기" }))
    const title = await screen.findByText("오늘 사용할 수 있는 AI 질문을 모두 사용했습니다.")
    const notice = title.closest("[role=status]") as HTMLElement
    expect(within(notice).getByRole("link", { name: "로그인" })).toBeTruthy()
    expect(within(notice).getByRole("link", { name: "회원가입" }).getAttribute("href")).toBe(
      "/signup",
    )
  })
})

describe("W-09 로그인 (Mock)", () => {
  it("틀리면 같은 오류 문구로 로그인되지 않고, 맞으면 헤더가 로그아웃으로 바뀐다", async () => {
    renderAt("/login")
    fireEvent.change(screen.getByLabelText("이메일"), { target: { value: MOCK_ACCOUNT.email } })
    fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "wrong-pass1" } })
    fireEvent.click(screen.getByRole("button", { name: "로그인" }))
    expect(await screen.findByText("이메일 또는 비밀번호를 확인해 주세요.")).toBeTruthy()
    expect(useAuthStore.getState().email).toBeNull()

    fireEvent.change(screen.getByLabelText("비밀번호"), {
      target: { value: MOCK_ACCOUNT.password },
    })
    fireEvent.click(screen.getByRole("button", { name: "로그인" }))
    expect(await screen.findByRole("button", { name: "로그아웃" })).toBeTruthy()
    expect(useAuthStore.getState().email).toBe(MOCK_ACCOUNT.email)
  })
})
