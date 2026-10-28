// @vitest-environment jsdom
// AI 대화 저장 변환 단위 테스트(3-6-1, D-14): 제목, 저장 규칙(답변·판단 유보·오류), 저장 기록 → 화면 복원.
import { act, renderHook, waitFor } from "@testing-library/react"
import { IDBFactory, IDBKeyRange } from "fake-indexeddb"
import { describe, expect, it, vi } from "vitest"
import { loadConsentStatuses } from "@/shared/storage/consent"
import { GUEST_NAMESPACE, InheritanceDb, type MessageRecord } from "@/shared/storage/db"
import {
  type ChatTurn,
  conversationTitle,
  conversationWriteInput,
  messagesToTurns,
  turnToMessages,
  useChatStorage,
} from "./chat-storage"

const answered: ChatTurn = {
  id: 100,
  question: "상속포기 기한이 언제부터인가요?",
  retries: 0,
  outcome: {
    kind: "answered",
    result: {
      state: "answered",
      answer: "일반적으로 3개월 안에…",
      sources: [
        { title: "법원 전자민원센터", url: "https://help.scourt.go.kr" },
        { title: "전화 상담 132", url: undefined },
      ],
    },
  },
}
const withheld: ChatTurn = {
  id: 200,
  question: "제 경우 기한이 지났나요?",
  retries: 0,
  outcome: { kind: "withheld", result: { state: "withheld", answer: null, sources: [] } },
}
const failed: ChatTurn = {
  id: 300,
  question: "실패한 질문",
  retries: 0,
  outcome: { kind: "error", failure: { status: 503, code: "PROVIDER_UNAVAILABLE", message: null } },
}

const asRecords = (messages: ReturnType<typeof turnToMessages>): MessageRecord[] =>
  (messages ?? []).map((message) => ({ ...message, namespace: "guest" }))

describe("conversationTitle (D-14)", () => {
  it("첫 질문 앞부분 30글자까지 쓰고 넘으면 …을 붙인다", () => {
    expect(conversationTitle("짧은 질문")).toBe("짧은 질문")
    expect(conversationTitle("가".repeat(31))).toBe(`${"가".repeat(30)}…`)
  })
})

describe("turnToMessages 저장 규칙", () => {
  it("검증된 답변은 본문과 출처를 저장하고 url이 없는 출처는 null로 남긴다", () => {
    const messages = turnToMessages("c1", answered, 10)
    expect(messages?.map((m) => m.role)).toEqual(["user", "assistant"])
    expect(messages?.[1].content).toBe("일반적으로 3개월 안에…")
    expect(messages?.[1].sources).toEqual([
      { title: "법원 전자민원센터", url: "https://help.scourt.go.kr" },
      { title: "전화 상담 132", url: null },
    ])
  })

  it("판단 유보는 질문만 저장하고 답변은 빈 값이다", () => {
    const messages = turnToMessages("c1", withheld, 10)
    expect(messages?.[1]).toMatchObject({ role: "assistant", content: "", sources: [] })
  })

  it("기술 오류·사용 제한은 저장하지 않는다", () => {
    expect(turnToMessages("c1", failed, 10)).toBeNull()
  })

  it("지금 대화에 저장할 질문이 없으면(오류뿐) 저장 입력이 없다", () => {
    expect(conversationWriteInput({ id: "c1", title: "t", createdAt: 1 }, [failed])).toBeNull()
  })
})

describe("messagesToTurns 복원", () => {
  it("답변·판단 유보를 그대로 되살리고 다시 연 질문으로 표시한다", () => {
    const records = [
      ...asRecords(turnToMessages("c1", answered, 10)),
      ...asRecords(turnToMessages("c1", withheld, 20)),
    ]

    const turns = messagesToTurns(records)

    expect(turns.map((turn) => [turn.id, turn.outcome.kind, turn.restored])).toEqual([
      [100, "answered", true],
      [200, "withheld", true],
    ])
    expect(turns[0].outcome.kind === "answered" && turns[0].outcome.result.sources?.[1]).toEqual({
      title: "전화 상담 132",
      url: undefined,
    })
  })
})

describe("출처 번호 [n] 저장·복원 (#184)", () => {
  it("본문의 [1]·[2]를 그대로 저장하고, 다시 열면 그대로 보인다", () => {
    const cited: ChatTurn = {
      ...answered,
      outcome: {
        kind: "answered",
        result: {
          state: "answered",
          answer: "가정법원에 신고합니다[1]. 기간을 확인하세요[2].",
          sources: answered.outcome.kind === "answered" ? answered.outcome.result.sources : [],
        },
      },
    }
    const turns = messagesToTurns(asRecords(turnToMessages("c1", cited, 10)))
    expect(turns[0].outcome.kind === "answered" && turns[0].outcome.result.answer).toBe(
      "가정법원에 신고합니다[1]. 기간을 확인하세요[2].",
    )
  })
})

describe("useChatStorage 동의 중 완료된 답변 (리뷰 회귀 P2)", () => {
  it("동의 처리가 끝나기 전에 끝난 답변도 동의가 확정되면 저장한다", async () => {
    const db = new InheritanceDb("chat-grant-race", { indexedDB: new IDBFactory(), IDBKeyRange })
    const { result } = renderHook(() => useChatStorage(db, GUEST_NAMESPACE))
    await waitFor(() => expect(result.current.status).toBe("not-consented"))
    const meta = { id: "c1", title: "상속포기 기한이 언제부터인가요?", createdAt: 1 }

    // [저장]을 누른 직후, 동의 저장이 끝나기 전에 답변이 끝나 저장을 요청한다.
    let granting: Promise<boolean> = Promise.resolve(false)
    act(() => {
      granting = result.current.grant(null, [])
    })
    const saving = result.current.saveTurn(meta, answered)
    await act(async () => {
      await granting
      await saving
    })

    expect(await db.messages.count()).toBe(2)
    expect((await db.conversations.get([GUEST_NAMESPACE, "c1"]))?.title).toBe(meta.title)
    db.close()
  })
})

describe("useChatStorage 삭제·철회 (4-3-2, 4-3-3, 4-3-4)", () => {
  const meta = { id: "c1", title: "질문", createdAt: 1 }

  const savingHook = async (name: string) => {
    const db = new InheritanceDb(name, { indexedDB: new IDBFactory(), IDBKeyRange })
    const hook = renderHook(() => useChatStorage(db, GUEST_NAMESPACE))
    await waitFor(() => expect(hook.result.current.status).toBe("not-consented"))
    await act(async () => {
      await hook.result.current.grant(meta, [answered])
    })
    await waitFor(() => expect(hook.result.current.conversations).toHaveLength(1))
    return { db, hook }
  }

  it("[대화 기록 삭제]는 대화만 지우고 동의는 유지해 이후 질문은 다시 저장된다", async () => {
    const { db, hook } = await savingHook("chat-remove-all")

    let ok = false
    await act(async () => {
      ok = await hook.result.current.removeAll()
    })

    expect(ok).toBe(true)
    expect(await db.conversations.count()).toBe(0)
    expect(hook.result.current.status).toBe("ready")
    await act(async () => {
      await hook.result.current.saveTurn({ ...meta, id: "c2" }, answered)
    })
    expect(await db.conversations.count()).toBe(1)
    db.close()
  })

  it("동의 철회는 대화와 동의를 지우고, 이후 질문은 저장하지 않는다", async () => {
    const { db, hook } = await savingHook("chat-revoke")

    await act(async () => {
      await hook.result.current.revoke()
    })

    expect(hook.result.current.status).toBe("not-consented")
    expect((await loadConsentStatuses(db, GUEST_NAMESPACE)).chat).toBe("not-consented")
    await act(async () => {
      await hook.result.current.saveTurn({ ...meta, id: "c2" }, answered)
    })
    expect(await db.messages.count()).toBe(0)
    db.close()
  })

  it("삭제가 실패하면 false이고 대화와 동의가 그대로다", async () => {
    const { db, hook } = await savingHook("chat-remove-fail")
    vi.spyOn(db.messages, "where").mockImplementation(() => {
      throw new Error("삭제 실패")
    })

    let removed = true
    let revoked = true
    await act(async () => {
      removed = await hook.result.current.removeAll()
      revoked = await hook.result.current.revoke()
    })

    vi.restoreAllMocks()
    expect([removed, revoked]).toEqual([false, false])
    expect(await db.conversations.count()).toBe(1)
    expect((await loadConsentStatuses(db, GUEST_NAMESPACE)).chat).toBe("ready")
    db.close()
  })
})

describe("리뷰 회귀 P2: 삭제 중 끝난 답변", () => {
  it("대화 전체 삭제를 시작한 뒤 끝난 이전 대화의 답변은 다시 저장하지 않는다", async () => {
    const db = new InheritanceDb("chat-remove-race", { indexedDB: new IDBFactory(), IDBKeyRange })
    const { result } = renderHook(() => useChatStorage(db, GUEST_NAMESPACE))
    await waitFor(() => expect(result.current.status).toBe("not-consented"))
    const meta = { id: "c1", title: "질문", createdAt: 1 }
    await act(async () => {
      await result.current.grant(meta, [answered])
    })

    // 삭제를 시작한 직후, 같은 대화의 진행 중이던 답변이 끝나 저장을 요청한다.
    await act(async () => {
      const removing = result.current.removeAll([meta.id])
      const saving = result.current.saveTurn(meta, { ...answered, id: 101 })
      await removing
      await saving
    })

    expect(await db.conversations.count()).toBe(0)
    expect(await db.messages.count()).toBe(0)
    db.close()
  })
})
