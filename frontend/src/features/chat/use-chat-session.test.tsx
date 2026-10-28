// @vitest-environment jsdom
// useChatSession 훅 단독 시험(#207): 화면 없이 대화 동작만 확인한다. 데이터 라우터 + Mock A08 + 메모리 IndexedDB.
// 실제 A08 Backend 연동 결과가 아니다.
import "fake-indexeddb/auto"
import { act, cleanup, render, waitFor } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useAuthStore } from "@/features/auth/auth-store"
import { createMockAskResponse, type MockAiScenario } from "@/mocks/ai-stream"
import { GUEST_NAMESPACE, inheritanceDb } from "@/shared/storage/db"
import { MAX_MANUAL_RETRIES } from "./chat-page"
import { useChatSessionStore } from "./chat-store"
import { type ChatSession, useChatSession } from "./use-chat-session"
import type { ChatTransport } from "./use-chat-stream"

let scenario: MockAiScenario = "answered"
let stepDelayMs = 0
// 보낸 요청을 센다(다시 시도 상한 확인용).
const transport = vi.fn<ChatTransport>((request, signal) =>
  createMockAskResponse(request, { scenario, signal, stepDelayMs }),
)

// 화면 없이 훅의 최신 값을 꺼내 보는 시험용 컴포넌트. useBlocker 때문에 데이터 라우터 안에서 그린다.
let session: ChatSession
function Probe() {
  session = useChatSession({ namespace: GUEST_NAMESPACE, transport })
  return null
}
const renderSession = () =>
  render(
    <RouterProvider
      router={createMemoryRouter([{ path: "/", element: <Probe /> }], { initialEntries: ["/"] })}
    />,
  )

const type = (text: string) => act(() => session.setInput(text))
const submit = () => act(() => session.submit())

beforeEach(async () => {
  await inheritanceDb.delete()
  await inheritanceDb.open()
  useAuthStore.getState().signOut()
  useChatSessionStore.setState({ externalNoticeAcknowledged: true, guestRemaining: 10 })
  scenario = "answered"
  stepDelayMs = 0
  transport.mockClear()
})
afterEach(cleanup)

describe("useChatSession 보내기", () => {
  it("질문을 보내면 입력칸을 비우고 답변을 대화에 남기며, 서버가 준 남은 횟수로 바꾼다", async () => {
    renderSession()
    await type("상속포기 기한")
    await submit()

    expect(session.input).toBe("")
    await waitFor(() => expect(session.turns).toHaveLength(1))
    expect(session.turns[0]).toMatchObject({
      question: "상속포기 기한",
      outcome: { kind: "answered" },
    })
    expect(session.pendingQuestion).toBeNull()
    expect(useChatSessionStore.getState().guestRemaining).toBe(9)
  })

  it("빈 질문은 보내지 않고 입력칸 오류를 보인다", async () => {
    renderSession()
    await type("   ")
    await submit()

    expect(session.inputError).toBe("질문을 입력해 주세요.")
    expect(transport).not.toHaveBeenCalled()
  })

  it("200자를 넘으면 보낼 수 없다", async () => {
    renderSession()
    await type("가".repeat(201))
    expect(session.overLimit).toBe(true)
    expect(session.canSend).toBe(false)

    await submit()
    expect(transport).not.toHaveBeenCalled()
  })

  it("외부 전송 안내를 확인하기 전에는 보낼 수 없다", async () => {
    useChatSessionStore.setState({ externalNoticeAcknowledged: false })
    renderSession()
    await type("상속세")
    expect(session.canSend).toBe(false)

    act(() => session.acknowledgeExternalNotice())
    expect(session.canSend).toBe(true)
  })
})

describe("useChatSession 취소·다시 시도", () => {
  it("진행 중인 질문을 취소하면 질문을 입력칸으로 돌려주고 대화에 남기지 않는다", async () => {
    stepDelayMs = 10_000
    renderSession()
    await type("취소할 질문")
    await submit()
    expect(session.pendingQuestion).toBe("취소할 질문")

    act(() => session.cancelQuestion())

    expect(session.input).toBe("취소할 질문")
    expect(session.cancelledNote).toBe(true)
    await waitFor(() => expect(session.running).toBe(false))
    expect(session.turns).toHaveLength(0)
  })

  it(`기술 오류(S6)는 같은 질문을 ${MAX_MANUAL_RETRIES}회까지만 다시 보내고, 대화에는 한 번만 남긴다`, async () => {
    scenario = "providerUnavailable"
    renderSession()
    await type("실패할 질문")
    await submit()
    await waitFor(() => expect(session.turns).toHaveLength(1))

    for (let attempt = 1; attempt <= MAX_MANUAL_RETRIES; attempt += 1) {
      act(() => session.retry(session.turns[0]))
      await waitFor(() => expect(session.turns[0]?.retries).toBe(attempt))
    }
    act(() => session.retry(session.turns[0]))

    expect(transport).toHaveBeenCalledTimes(1 + MAX_MANUAL_RETRIES)
    expect(session.turns).toHaveLength(1)
    expect(session.turns[0].outcome.kind).toBe("error")
  })
})

describe("useChatSession S7·S9", () => {
  it("출처가 없으면 판단 유보(S7)로 남는다", async () => {
    scenario = "withheld"
    renderSession()
    await type("판단 유보 질문")
    await submit()

    await waitFor(() => expect(session.turns[0]?.outcome.kind).toBe("withheld"))
  })

  it("비로그인 하루 한도(S9)를 받으면 남은 횟수를 0으로 두고 더 보낼 수 없다", async () => {
    scenario = "guestLimit"
    renderSession()
    await type("열한 번째 질문")
    await submit()

    await waitFor(() => expect(session.guestLimitReached).toBe(true))
    expect(useChatSessionStore.getState().guestRemaining).toBe(0)
    await type("다음 질문")
    expect(session.canSend).toBe(false)
  })
})

describe("useChatSession 새 대화·저장", () => {
  it("저장하지 않은 대화가 있으면 새 대화 전에 확인하고, 확인하면 대화를 비운다(S8)", async () => {
    renderSession()
    await type("첫 질문")
    await submit()
    await waitFor(() => expect(session.turns).toHaveLength(1))

    act(() => session.requestNewChat())
    expect(session.confirmingNewChat).toBe(true)
    expect(session.turns).toHaveLength(1)

    act(() => session.confirmNewChat())
    expect(session.confirmingNewChat).toBe(false)
    expect(session.turns).toHaveLength(0)
    expect(session.meta).toBeNull()
  })

  it("대화도 입력도 없으면 확인 없이 새 대화를 연다", () => {
    renderSession()
    act(() => session.requestNewChat())
    expect(session.confirmingNewChat).toBe(false)
  })

  it("저장에 동의하기 전에는 대화를 저장하지 않고, 동의하면 지금 대화를 함께 저장한다", async () => {
    renderSession()
    await waitFor(() => expect(session.storage.status).toBe("not-consented"))
    await type("저장할 질문")
    await submit()
    await waitFor(() => expect(session.turns).toHaveLength(1))
    expect(await inheritanceDb.conversations.count()).toBe(0)

    await act(async () => {
      expect(await session.grantStorage()).toBe(true)
    })

    expect(session.saving).toBe(true)
    const saved = await inheritanceDb.conversations.toArray()
    expect(saved).toHaveLength(1)
    expect(saved[0].title).toContain("저장할 질문")
  })
})
