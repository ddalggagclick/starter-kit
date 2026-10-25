// AI 대화 저장 변환 단위 테스트(3-6-1, D-14): 제목, 저장 규칙(답변·판단 유보·오류), 저장 기록 → 화면 복원.
import { describe, expect, it } from "vitest"
import type { MessageRecord } from "@/shared/storage/db"
import {
  type ChatTurn,
  conversationTitle,
  conversationWriteInput,
  messagesToTurns,
  turnToMessages,
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
