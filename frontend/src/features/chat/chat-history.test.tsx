// @vitest-environment jsdom
// W-07 AI 대화 저장 흐름 테스트(4-1-1, 3-6-1~3-6-3, S8·S10·S11): 실제 라우터 + Mock A08 + 메모리 IndexedDB.
// 실제 브라우저·Backend 검증이 아니다. Mock 답변은 이벤트마다 지연이 있어 몇 초씩 걸린다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import { useAuthStore } from "@/features/auth/auth-store"
import { useMockAiScenarioStore } from "@/mocks/mock-ai-scenario"
import { resetMockApiState } from "@/mocks/mock-api"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { grantConsent } from "@/shared/storage/consent"
import { accountNamespace, GUEST_NAMESPACE, inheritanceDb } from "@/shared/storage/db"
import { ChatConsentBand } from "./chat-history"
import { useChatSessionStore } from "./chat-store"

const ANSWER_TIMEOUT = { timeout: 6000 }

const renderAi = () => {
  const router = createMemoryRouter(appRoutes, { initialEntries: ["/ai"] })
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return router
}

// 질문을 보내고 그 질문의 Mock 답변(타이핑 완료 후 출처까지)이 보일 때까지 기다린다.
// 이미 보이는 답변과 구분하려고 '공식 출처' 개수가 하나 늘 때까지 기다린다.
const ask = async (question: string) => {
  const before = screen.queryAllByText("공식 출처").length
  fireEvent.change(screen.getByLabelText("질문"), { target: { value: question } })
  fireEvent.click(screen.getByRole("button", { name: "보내기" }))
  await waitFor(
    () => expect(screen.queryAllByText("공식 출처").length).toBe(before + 1),
    ANSWER_TIMEOUT,
  )
}

const consentInBand = async () => {
  const band = await screen.findByRole("region", { name: "AI 대화 저장" })
  // #197: 동의는 [저장 설정]을 눌러 여는 모달에서 받는다(모달은 띠 안에 그려진다).
  fireEvent.click(within(band).getByRole("button", { name: "저장 설정" }))
  fireEvent.click(within(band).getByLabelText("AI 대화 저장 정책을 확인했습니다"))
  fireEvent.click(within(band).getByRole("button", { name: "저장" }))
  await screen.findByText(/AI 대화 저장: ● 이 기기에 저장 중/)
}

const conversationCount = (namespace = GUEST_NAMESPACE) =>
  inheritanceDb.conversations.where("namespace").equals(namespace).count()

beforeEach(async () => {
  await inheritanceDb.delete()
  await inheritanceDb.open()
  resetMockApiState()
  useInheritanceStore.getState().reset()
  useAuthStore.getState().signOut()
  useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 10 })
  useMockAiScenarioStore.setState({ scenario: "answered" })
})
afterEach(cleanup)

describe("AI 대화 저장 동의 (4-1-1, D-03)", () => {
  it("체크리스트 동의만 있으면 AI 대화는 저장하지 않는다", async () => {
    await grantConsent(inheritanceDb, GUEST_NAMESPACE, "checklist")
    renderAi()
    await screen.findByRole("region", { name: "AI 대화 저장" })

    await ask("상속세")

    expect(await conversationCount()).toBe(0)
  }, 15_000)

  it("동의하면 지금 대화를 저장하고, 이후 질문도 저장하며, 다시 열면 목록에서 타이핑 없이 복원된다", async () => {
    renderAi()
    await ask("상속포기 기한이 언제부터인가요?")
    await consentInBand()
    expect(await conversationCount()).toBe(1)

    await ask("서류는 무엇이 필요한가요?")
    await waitFor(async () =>
      expect(await inheritanceDb.messages.where("namespace").equals(GUEST_NAMESPACE).count()).toBe(
        4,
      ),
    )
    cleanup()

    // 재방문
    renderAi()
    fireEvent.click(await screen.findByRole("button", { name: /이전 대화/ }))
    const list = await screen.findByRole("list", { name: "이전 대화" })
    fireEvent.click(
      within(list).getByRole("button", { name: /^\d+\/\d+ · 상속포기 기한이 언제부터인가요/ }),
    )

    // 저장된 두 질문과 답변이 바로(타이핑 없이) 보인다.
    expect(await screen.findByText("서류는 무엇이 필요한가요?")).toBeTruthy()
    expect(screen.getAllByText("공식 출처")).toHaveLength(2)
  }, 20_000)

  it("이전 대화를 하나씩 지울 수 있다(S08-A)", async () => {
    renderAi()
    await consentInBand()
    await ask("상속세")
    await waitFor(async () => expect(await conversationCount()).toBe(1))

    fireEvent.click(screen.getByRole("button", { name: /이전 대화/ }))
    fireEvent.click(await screen.findByRole("button", { name: "삭제: 상속세" }))

    expect(await screen.findByText("저장된 대화가 없습니다.")).toBeTruthy()
    expect(await conversationCount()).toBe(0)
  }, 15_000)
})

describe("W-07 삭제·철회 (4-3-1~4-3-3)", () => {
  it("[대화 기록 삭제]는 대화를 지우고 저장 중 상태를 유지한다", async () => {
    renderAi()
    await consentInBand()
    await ask("상속세")
    await waitFor(async () => expect(await conversationCount()).toBe(1))

    fireEvent.click(screen.getByRole("button", { name: "대화 기록 삭제" }))
    fireEvent.click(await screen.findByRole("button", { name: "삭제: AI 대화 기록" }))

    expect(
      await screen.findByText(/AI 대화 기록을 삭제했습니다. 저장 동의는 유지됩니다/),
    ).toBeTruthy()
    expect(await conversationCount()).toBe(0)
    expect(screen.queryByText("공식 출처")).toBeNull()
    expect(screen.getByText(/AI 대화 저장: ● 이 기기에 저장 중/)).toBeTruthy()
  }, 15_000)

  it("동의 철회 뒤 대화가 지워지고 동의 띠가 다시 나타난다", async () => {
    renderAi()
    await consentInBand()
    await ask("상속세")
    await waitFor(async () => expect(await conversationCount()).toBe(1))

    fireEvent.click(screen.getByRole("button", { name: "AI 대화 저장 동의 철회" }))
    fireEvent.click(await screen.findByRole("button", { name: "동의 철회: AI 대화 기록 삭제" }))

    expect(
      await screen.findByText(/저장 동의를 철회하고 이 기기의 AI 대화 기록을 삭제했습니다/),
    ).toBeTruthy()
    expect(await screen.findByRole("region", { name: "AI 대화 저장" })).toBeTruthy()
    expect(await conversationCount()).toBe(0)
  }, 15_000)
})

describe("새 대화 시작 (S8)", () => {
  it("저장 중이면 확인 없이 새 대화를 열고 이전 대화는 목록에 남는다", async () => {
    renderAi()
    await consentInBand()
    await ask("상속세")
    await waitFor(async () => expect(await conversationCount()).toBe(1))

    fireEvent.click(screen.getByRole("button", { name: "새 대화 시작" }))

    expect(screen.queryByRole("dialog")).toBeNull()
    expect(screen.queryByText("공식 출처")).toBeNull()
    expect(await conversationCount()).toBe(1)
  }, 15_000)

  it("저장 중이어도 보내지 않은 입력이 있으면 묻는다", async () => {
    renderAi()
    await consentInBand()
    fireEvent.change(screen.getByLabelText("질문"), { target: { value: "보내지 않은 질문" } })

    fireEvent.click(screen.getByRole("button", { name: "새 대화 시작" }))

    expect(await screen.findByRole("dialog")).toBeTruthy()
  })

  it("저장하지 않는 중에 대화가 있으면 사라진다고 묻는다", async () => {
    renderAi()
    await ask("상속세")

    fireEvent.click(screen.getByRole("button", { name: "새 대화 시작" }))

    const dialog = await screen.findByRole("dialog")
    expect(within(dialog).getByText(/저장되지 않아 새 대화를 시작하면 사라집니다/)).toBeTruthy()
    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }))
    expect(within(screen.getByRole("region", { name: "대화" })).getByText("상속세")).toBeTruthy()
  }, 15_000)
})

describe("저장 안 된 대화 이탈 확인 (S11, D-11)", () => {
  const leaveTo = (label: string) =>
    fireEvent.click(
      within(screen.getByRole("navigation", { name: "주요 메뉴" })).getByRole("link", {
        name: label,
      }),
    )

  it("미동의 상태에서 대화가 있으면 사이트 안 이동 때 묻고, 취소하면 머문다", async () => {
    const router = renderAi()
    await ask("상속세")

    leaveTo("체크리스트")
    const dialog = await screen.findByRole("dialog")
    expect(within(dialog).getByText("이 대화는 저장되지 않아 나가면 사라집니다.")).toBeTruthy()

    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    expect(router.state.location.pathname).toBe("/ai")
  }, 15_000)

  it("[저장 없이 이동]은 저장하지 않고 이동한다", async () => {
    const router = renderAi()
    await ask("상속세")

    leaveTo("체크리스트")
    fireEvent.click(await screen.findByRole("button", { name: "저장 없이 이동" }))

    await waitFor(() => expect(router.state.location.pathname).toBe("/checklist"))
    expect(await conversationCount()).toBe(0)
  }, 15_000)

  it("[이 기기에 저장하고 이동]은 동의와 대화를 저장한 뒤 이동한다", async () => {
    const router = renderAi()
    await ask("상속세")

    leaveTo("체크리스트")
    fireEvent.click(await screen.findByRole("button", { name: "이 기기에 저장하고 이동" }))

    await waitFor(() => expect(router.state.location.pathname).toBe("/checklist"))
    expect(await conversationCount()).toBe(1)
  }, 15_000)

  it("저장 중이거나 대화·입력이 없으면 묻지 않고 이동한다", async () => {
    const router = renderAi()
    await screen.findByRole("region", { name: "AI 대화 저장" })
    leaveTo("체크리스트")
    await waitFor(() => expect(router.state.location.pathname).toBe("/checklist"))
  })
})

describe("리뷰 회귀", () => {
  it("P1: 저장하지 않은 임시 대화도 로그아웃하면 화면에서 지운다", async () => {
    act(() => useAuthStore.getState().signIn({ accountId: "user-a", email: "a@example.com" }))
    renderAi()
    await ask("A의 임시 질문")

    act(() => useAuthStore.getState().signOut())

    await waitFor(() => expect(screen.queryByText("A의 임시 질문")).toBeNull())
  }, 15_000)

  it("P2: 실패한(S6) 첫 질문은 제목이 되지 않고, 처음 저장되는 성공 질문이 제목이 된다", async () => {
    // #205: 화면 드롭다운 대신 시험 코드에서 Mock 응답 시나리오를 정한다.
    useMockAiScenarioStore.setState({ scenario: "providerUnavailable" })
    renderAi()
    fireEvent.change(screen.getByLabelText("질문"), { target: { value: "실패한 첫 질문" } })
    fireEvent.click(screen.getByRole("button", { name: "보내기" }))
    await screen.findByText("일시적인 문제로 답변하지 못했습니다.")

    act(() => useMockAiScenarioStore.setState({ scenario: "answered" }))
    await ask("성공한 질문")
    await consentInBand()

    const saved = await inheritanceDb.conversations
      .where("namespace")
      .equals(GUEST_NAMESPACE)
      .toArray()
    expect(saved.map((conversation) => conversation.title)).toEqual(["성공한 질문"])
  }, 15_000)
})

describe("계정별 대화 분리 (4-2-2)", () => {
  it("A가 저장한 대화는 로그아웃·B 로그인 뒤 화면과 목록에 보이지 않는다", async () => {
    act(() => useAuthStore.getState().signIn({ accountId: "user-a", email: "a@example.com" }))
    renderAi()
    await consentInBand()
    await ask("A의 질문")
    await waitFor(async () => expect(await conversationCount(accountNamespace("user-a"))).toBe(1))

    act(() => useAuthStore.getState().signOut())
    await waitFor(() => expect(screen.queryByText("A의 질문")).toBeNull())

    act(() => useAuthStore.getState().signIn({ accountId: "user-b", email: "b@example.com" }))
    // B는 대화 저장 동의 전이라 이전 대화 목록 자체가 없다.
    await screen.findByRole("region", { name: "AI 대화 저장" })
    expect(screen.queryByRole("button", { name: /이전 대화/ })).toBeNull()
    expect(screen.queryByText("A의 질문")).toBeNull()
  }, 15_000)
})

// #197: 동의 모달 자체 동작. 저장 흐름 전체는 위 화면 테스트가 확인한다.
describe("ChatConsentBand 모달 (#197)", () => {
  it("[저장 설정]을 눌러야 모달이 열리고, 체크 전에는 [저장]이 막히며, Esc로 닫으면 고르지 않은 것이다", () => {
    const onDecline = vi.fn()
    render(
      <ChatConsentBand
        status="not-consented"
        declined={false}
        onGrant={vi.fn(async () => true)}
        onDecline={onDecline}
      />,
    )

    expect(screen.queryByRole("dialog")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "저장 설정" }))
    expect(screen.getByRole("dialog", { name: "AI 대화를 이 기기에 저장할까요?" })).toBeTruthy()
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true)

    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(onDecline).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "저장 설정" })).toBeTruthy()
  })
})
