// @vitest-environment jsdom
// 대화 공용 부품·규칙 시험(#225): 출처 목록, 422 입력 오류 문구, 429 제한 사유 구분.
// chat-page.test.tsx(쓰지 않는 /ai 화면 시험)에만 있던 확인 항목을 공용 부품 파일(chat-parts.tsx) 기준으로 옮겼다.
// 확인 내용은 원래 시험과 같다. 실제 A08 Backend 연동 결과가 아니다.
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { inputErrorMessage, rateLimitKind, Sources } from "./chat-parts"

afterEach(cleanup)

describe("Sources 출처 목록", () => {
  it("url이 있으면 새 탭 링크, url이 null이면 링크 없이 제목만 보인다", () => {
    render(
      <Sources
        sources={[
          { title: "대한법률구조공단 · 전화 상담 132", url: null },
          { title: "법원 전자민원센터", url: "https://help.scourt.go.kr" },
        ]}
      />,
    )

    const links = screen.getAllByRole("link")
    expect(links).toHaveLength(1)
    expect(links[0].getAttribute("href")).toBe("https://help.scourt.go.kr")
    expect(links[0].getAttribute("target")).toBe("_blank")
    const phone = screen.getByText("대한법률구조공단 · 전화 상담 132")
    expect(phone.closest("a")).toBeNull()
  })

  it("url이 null인 출처가 여럿이어도 모두 보이고, 2개를 넘으면 추가 출처 보기로 접는다", () => {
    render(
      <Sources
        sources={[
          { title: "전화 상담 A", url: null },
          { title: "전화 상담 B", url: null },
          { title: "전화 상담 C", url: null },
        ]}
      />,
    )

    expect(screen.getByText("전화 상담 A")).toBeTruthy()
    expect(screen.getByText("전화 상담 B")).toBeTruthy()
    expect(screen.queryByText("전화 상담 C")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "추가 출처 보기 (1)" }))
    expect(screen.getByText("전화 상담 C")).toBeTruthy()
    expect(screen.queryAllByRole("link")).toHaveLength(0)
  })
})

describe("422 입력 오류 문구", () => {
  it("서버 message가 코드 이름뿐이면 코드를 보이지 않고 안내 문구를 쓴다", () => {
    const message = inputErrorMessage({
      status: 422,
      code: "VALIDATION_ERROR",
      message: "VALIDATION_ERROR",
    })
    expect(message).not.toContain("VALIDATION_ERROR")
    expect(message).toContain("200자")
  })

  it("서버가 사람이 읽을 문장을 보내면 그대로 쓴다", () => {
    expect(
      inputErrorMessage({
        status: 422,
        code: "VALIDATION_ERROR",
        message: "질문을 입력해 주세요.",
      }),
    ).toBe("질문을 입력해 주세요.")
  })
})

describe("429 제한 사유 구분 (3-7-3)", () => {
  it("제한 사유는 message로 정하고, 사유가 없으면 로그인 여부로 정한다", () => {
    const failure = (message: string | null) => ({ status: 429, code: "RATE_LIMITED", message })
    expect(rateLimitKind(failure("MEMBER_MINUTE_LIMIT"), false)).toBe("memberMinute")
    // 화면의 로그인 상태와 서버 판단이 다르면 서버가 보낸 사유를 따른다.
    expect(rateLimitKind(failure("MEMBER_MINUTE_LIMIT"), true)).toBe("memberMinute")
    expect(rateLimitKind(failure("GUEST_DAILY_LIMIT"), false)).toBe("guestDaily")
    expect(rateLimitKind(failure("GUEST_DAILY_LIMIT"), true)).toBe("guestDaily")
    // 사유를 보내지 않는 서버(message가 코드 이름뿐이거나 없음)
    expect(rateLimitKind(failure("RATE_LIMITED"), true)).toBe("guestDaily")
    expect(rateLimitKind(failure(null), false)).toBe("memberMinute")
  })
})
