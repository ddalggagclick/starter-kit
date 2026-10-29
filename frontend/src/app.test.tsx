// @vitest-environment jsdom
// V1 화면 흐름 스모크 테스트(jsdom + Mock 데이터). 실제 브라우저·Backend 검증을 대신하지 않는다.
import { QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
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
  // #227 최신 시안: 관계와 안심상속을 고르기 전에는 [체크리스트 보기]가 눌리지 않고 이유를 한 줄로 보인다.
  it("관계와 안심상속을 고르기 전에는 [체크리스트 보기]가 막히고 이유를 보인다", () => {
    const router = renderAt("/start")
    const submit = screen.getByRole("button", { name: "체크리스트 보기" }) as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    expect(screen.getByText("관계와 안심상속 여부를 고르면 다음 단계로 갈 수 있어요.")).toBeTruthy()
    fireEvent.click(screen.getByLabelText("배우자"))
    expect(submit.disabled).toBe(true)
    fireEvent.click(screen.getByLabelText("모르겠어요", { selector: "input[type=radio]" }))
    expect(submit.disabled).toBe(false)
    expect(screen.getByText("좋아요. 체크리스트를 만들었어요.")).toBeTruthy()
    expect(router.state.location.pathname).toBe("/start")
  })

  it("사망일을 비워 두면 '모름'으로 저장하고 체크리스트로 간다", async () => {
    const router = renderAt("/start")
    fireEvent.click(screen.getByLabelText("부모"))
    fireEvent.click(screen.getByLabelText("신청했어요"))
    fireEvent.click(screen.getByRole("button", { name: "체크리스트 보기" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/checklist"))
    expect(useInheritanceStore.getState().answers).toMatchObject({
      relationship: "ascendant",
      deathDate: null,
      deathDateUnknown: true,
      oneStopApplication: "yes",
    })
    // [모두 건너뛰고 보기]는 사용자 결정으로 뺐다.
    expect(screen.queryByRole("button", { name: "모두 건너뛰고 보기" })).toBeNull()
  })

  it("세 답을 고르면 W-02에 공통 절차 8개와 공통 위험 경고가 보인다", async () => {
    const router = renderAt("/start")
    fireEvent.click(screen.getByLabelText("배우자"))
    fireEvent.click(screen.getByLabelText("모르겠어요", { selector: "input[type=checkbox]" }))
    fireEvent.click(screen.getByLabelText("신청하지 않았어요"))
    fireEvent.click(screen.getByRole("button", { name: "체크리스트 보기" }))
    await waitFor(() => expect(router.state.location.pathname).toBe("/checklist"))
    await screen.findByText("부동산 상속", {}, { timeout: 2000 })
    // #227: 절차 8개는 항목 전체가 상세로 가는 링크다(이름 = 절차 이름).
    expect(
      within(screen.getByRole("region", { name: "상속 공통 절차" })).getAllByRole("link"),
    ).toHaveLength(8)
    expect(screen.getAllByText(/기한 · 채무는 공식 자료로 확인하세요/).length).toBeGreaterThan(0)
    expect(screen.getByText("배우자")).toBeTruthy()
  })

  it("읽음 버튼을 눌러도 카드 순서·개수는 그대로이고 읽음 진행만 바뀐다", async () => {
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
    const names = () =>
      within(screen.getByRole("region", { name: "상속 공통 절차" }))
        .getAllByRole("link")
        .map((link) => link.textContent)
    const before = names()
    expect(screen.getByText("0/8 읽음")).toBeTruthy()
    // #227: 체크리스트 [읽음] 버튼은 늘 "읽음"이고 눌림 상태(aria-pressed)로 구분한다.
    fireEvent.click(screen.getAllByRole("button", { name: /^읽음/, pressed: false })[0])
    expect(screen.getByText("1/8 읽음")).toBeTruthy()
    expect(
      screen.getByRole("progressbar", { name: "절차 안내 읽음" }).getAttribute("aria-valuenow"),
    ).toBe("1")
    expect(names()).toEqual(before)
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
    // #227 최신 시안: 필요 서류·신청 방법은 펼치고 예외·참고·문의처는 접는다.
    expect(sections.map((d) => d.open)).toEqual([true, true, false, false])
  })

  it("p02는 대법원 전자가족관계등록시스템·정부24 공식 링크를 새 탭으로 보이고 링크 없음 안내는 없다", async () => {
    renderAt("/procedures/p02")
    const sources = await screen.findByRole("region", { name: "공식 출처" })
    const links = within(sources).getAllByRole("link")
    // 2026-10-26 B1 확인 링크(요청 원문 순서)
    expect(
      links.map((link) => [
        link.textContent?.replace("(새 창)", "").trim(),
        link.getAttribute("href"),
      ]),
    ).toEqual([
      ["대법원 전자가족관계등록시스템", "https://efamily.scourt.go.kr/"],
      ["정부24", "https://www.gov.kr/"],
    ])
    expect(links.every((link) => link.getAttribute("target") === "_blank")).toBe(true)
    expect(within(sources).queryByText(/연결할 공식 안내 페이지가 없습니다/)).toBeNull()
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
    // #227: 외부 전송 안내는 개인정보 경고와 한 줄로 합쳐지고 버튼 이름은 [확인]이다.
    fireEvent.click(screen.getByRole("button", { name: "확인" }))
    expect(send.disabled).toBe(false)
    fireEvent.change(screen.getByLabelText("질문"), { target: { value: "가".repeat(201) } })
    expect(screen.getByText(/201\/200자/)).toBeTruthy()
    expect(send.disabled).toBe(true)
  })

  // #211: /ai는 첫 화면 대화창으로 합쳐졌다. 예시 질문 시험은 첫 화면 예시 질문 이슈(⑤)에서 다시 넣는다.
  it("예전 주소 /ai는 첫 화면 대화창(/#ai)으로 바꿔 보낸다", async () => {
    const router = renderAt("/ai")
    await waitFor(() => expect(router.state.location.pathname).toBe("/"))
    expect(router.state.location.hash).toBe("#ai")
    expect(screen.getByRole("region", { name: "AI에게 질문하기" }).closest("#ai")).toBeTruthy()
    // 기록을 바꿔치기해 뒤로 가기로 /ai에 되돌아가 다시 이동하는 반복이 없다.
    expect(router.state.historyAction).toBe("REPLACE")
  })

  it("주소에 #ai가 있으면 대화창 위치로 화면을 내린다", () => {
    // jsdom에는 scrollIntoView가 없어 시험용으로 넣는다.
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    renderAt("/#ai")
    expect(scrollIntoView).toHaveBeenCalled()
    expect(scrollIntoView.mock.contexts[0]).toBe(document.getElementById("ai"))
    // 다른 시험에 영향이 없도록 넣었던 함수를 지운다.
    delete (Element.prototype as Partial<Element>).scrollIntoView
  })

  // #227: 헤더 메뉴는 왼쪽 사이드바로 옮겼다. [체크리스트]는 페이지, 나머지 3개는 화면 위 모달이다. [AI 질문]은 없다.
  it("사이드바 주요 메뉴는 체크리스트·전체 절차·상속 관계·상속세이고 [AI 질문]은 없다", () => {
    renderAt("/")
    const nav = screen.getByRole("navigation", { name: "주요 메뉴" })
    expect(within(nav).queryByText("AI 질문")).toBeNull()
    expect(within(nav).getByRole("link", { name: "체크리스트" }).getAttribute("href")).toBe(
      "/checklist",
    )
    for (const name of ["전체 절차", "상속 관계", "상속세"]) {
      expect(within(nav).getByRole("button", { name }).getAttribute("aria-haspopup")).toBe("dialog")
    }
  })

  it("[전체 절차]는 페이지 이동 없이 모달로 열고, 모달 안 절차를 누르면 모달을 닫고 절차 상세로 간다", async () => {
    const router = renderAt("/")
    const nav = screen.getByRole("navigation", { name: "주요 메뉴" })
    fireEvent.click(within(nav).getByRole("button", { name: "전체 절차" }))

    const dialog = screen.getByRole("dialog", { name: "전체 절차" })
    expect(router.state.location.pathname).toBe("/")
    expect(within(dialog).getByRole("heading", { name: "상속 공통 절차" })).toBeTruthy()
    // 첫 절차를 펼치면 그때 상세를 불러와 핵심 안내와 [상세 보기]가 보인다.
    const first = (await within(dialog).findByText("사망 관련 행정")).closest(
      "details",
    ) as HTMLDetailsElement
    first.open = true
    fireEvent(first, new Event("toggle"))
    fireEvent.click(await within(dialog).findByRole("link", { name: "상세 보기" }))

    await waitFor(() => expect(router.state.location.pathname).toBe("/procedures/p01"))
    expect(screen.queryByRole("dialog", { name: "전체 절차" })).toBeNull()
  })

  it("[상속 관계]·[상속세] 모달은 Esc와 [닫기]로 닫히고 초점은 누른 메뉴로 돌아온다", () => {
    renderAt("/")
    const nav = screen.getByRole("navigation", { name: "주요 메뉴" })
    const relation = within(nav).getByRole("button", { name: "상속 관계" })
    relation.focus()
    fireEvent.click(relation)
    expect(screen.getByRole("dialog", { name: "상속 관계" })).toBeTruthy()
    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(document.activeElement).toBe(relation)

    fireEvent.click(within(nav).getByRole("button", { name: "상속세" }))
    const tax = screen.getByRole("dialog", { name: "상속세" })
    // 오른쪽 위 X와 아래쪽 [닫기]가 있다. 아래쪽 [닫기]로 닫는다.
    fireEvent.click(within(tax).getAllByRole("button", { name: "닫기" }).at(-1) as HTMLElement)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("사이드바를 접으면 글자는 화면에서만 감추고 메뉴 이름은 그대로 읽힌다", () => {
    renderAt("/")
    const toggle = screen.getByRole("button", { name: "사이드바 접기" })
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
    fireEvent.click(toggle)
    expect(
      screen.getByRole("button", { name: "사이드바 펼치기" }).getAttribute("aria-expanded"),
    ).toBe("false")
    const nav = screen.getByRole("navigation", { name: "주요 메뉴" })
    expect(within(nav).getByRole("link", { name: "체크리스트" })).toBeTruthy()
    expect(within(nav).getByText("체크리스트").className).toContain("sr-only")
  })

  it("좁은 화면 [메뉴 열기]는 왼쪽 메뉴 서랍을 열고, 메뉴를 고르면 닫힌다", () => {
    renderAt("/")
    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }))
    const drawer = screen.getByRole("dialog", { name: "메뉴" })
    fireEvent.click(within(drawer).getByRole("button", { name: "상속세" }))
    expect(screen.queryByRole("dialog", { name: "메뉴" })).toBeNull()
    expect(screen.getByRole("dialog", { name: "상속세" })).toBeTruthy()
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
    fireEvent.click(within(screen.getByRole("main")).getByRole("button", { name: "로그인" }))
    expect(await screen.findByText("이메일 또는 비밀번호를 확인해 주세요.")).toBeTruthy()
    expect(useAuthStore.getState().email).toBeNull()

    fireEvent.change(screen.getByLabelText("비밀번호"), {
      target: { value: MOCK_ACCOUNT.password },
    })
    fireEvent.click(within(screen.getByRole("main")).getByRole("button", { name: "로그인" }))
    // #227: 데스크톱 사이드바와 모바일 위쪽 줄에 [로그아웃]이 하나씩 있다(화면 폭에 따라 하나만 보인다).
    expect((await screen.findAllByRole("button", { name: "로그아웃" })).length).toBeGreaterThan(0)
    expect(useAuthStore.getState().email).toBe(MOCK_ACCOUNT.email)
  })
})

// #227 새 시안: 로그인·답변 수정 등은 지금 화면 위 모달로 열리고, 끝나면 보던 화면에 그대로 머문다.
describe("모달로 여는 화면 (#227)", () => {
  const answers = {
    relationship: "descendant",
    deathDate: "2026-09-30",
    deathDateUnknown: false,
    oneStopApplication: "yes",
  } as const

  it("사이드바 [로그인]은 모달로 열리고, [회원가입]으로 바꿀 수 있으며, 로그인하면 보던 화면에 머문다", async () => {
    useInheritanceStore.getState().setInitialAnswers(answers, "direct")
    const router = renderAt("/checklist")
    const sidebar = screen.getByRole("complementary", { name: "사이드바" })
    fireEvent.click(within(sidebar).getByRole("button", { name: "로그인" }))

    let dialog = screen.getByRole("dialog", { name: "로그인" })
    fireEvent.click(within(dialog).getByRole("button", { name: "회원가입" }))
    dialog = screen.getByRole("dialog", { name: "회원가입" })
    fireEvent.click(within(dialog).getByRole("button", { name: "이미 계정이 있으면 로그인" }))
    dialog = screen.getByRole("dialog", { name: "로그인" })

    fireEvent.change(within(dialog).getByLabelText("이메일"), {
      target: { value: MOCK_ACCOUNT.email },
    })
    fireEvent.change(within(dialog).getByLabelText("비밀번호"), {
      target: { value: MOCK_ACCOUNT.password },
    })
    fireEvent.click(within(dialog).getByRole("button", { name: "로그인" }))

    await waitFor(() => expect(useAuthStore.getState().email).toBe(MOCK_ACCOUNT.email))
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(router.state.location.pathname).toBe("/checklist")
  })

  it("체크리스트 [답변 수정]은 모달로 열리고, 반영하면 모달만 닫히며 체크리스트에 머문다", async () => {
    useInheritanceStore.getState().setInitialAnswers(answers, "direct")
    const router = renderAt("/checklist")
    await screen.findByText("부동산 상속", {}, { timeout: 2000 })
    fireEvent.click(screen.getByRole("button", { name: "답변 수정" }))

    const dialog = screen.getByRole("dialog", { name: "상속 절차 시작" })
    fireEvent.click(within(dialog).getByLabelText("배우자"))
    fireEvent.click(within(dialog).getByRole("button", { name: "수정 내용 반영" }))

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    expect(router.state.location.pathname).toBe("/checklist")
    expect(useInheritanceStore.getState().answers?.relationship).toBe("spouse")
  })

  it("좁은 화면용 ✓ 버튼도 [읽기 전/읽음]과 같은 읽음 상태를 바꾼다", async () => {
    useInheritanceStore.getState().setInitialAnswers(answers, "direct")
    renderAt("/checklist")
    await screen.findByText("부동산 상속", {}, { timeout: 2000 })
    const check = screen.getByRole("button", { name: "사망 관련 행정 읽음 표시" })
    expect(check.getAttribute("aria-pressed")).toBe("false")
    fireEvent.click(check)
    expect(check.getAttribute("aria-pressed")).toBe("true")
    expect(screen.getByText("1/8 읽음")).toBeTruthy()
  })
})

describe("답하기 전 [체크리스트] (#227 최신 시안)", () => {
  it("아직 답하지 않았으면 사이드바 [체크리스트]는 이동하지 않고 질문 3개 모달을 연다", () => {
    const router = renderAt("/")
    const nav = screen.getByRole("navigation", { name: "주요 메뉴" })
    fireEvent.click(within(nav).getByRole("link", { name: "체크리스트" }))
    expect(screen.getByRole("dialog", { name: "상속 절차 시작" })).toBeTruthy()
    expect(router.state.location.pathname).toBe("/")
  })
})

describe("체크리스트 입장 순서 (#227 사용자 요청)", () => {
  it("답하기 전에 체크리스트 주소로 들어오면 질문 3개 모달이 먼저 뜬다", async () => {
    renderAt("/checklist")
    expect(await screen.findByRole("dialog", { name: "상속 절차 시작" })).toBeTruthy()
  })
})

describe("사이드바 [홈] (#227 사용자 요청)", () => {
  it("[홈]은 첫 화면으로 가고, 첫 화면에서만 선택 표시된다", async () => {
    const router = renderAt("/procedures/p01")
    const nav = screen.getByRole("navigation", { name: "주요 메뉴" })
    const home = within(nav).getByRole("link", { name: "홈" })
    expect(home.getAttribute("aria-current")).toBeNull()
    // 절차 상세에서는 [체크리스트]가 선택 표시된다.
    expect(within(nav).getByRole("link", { name: "체크리스트" }).getAttribute("aria-current")).toBe(
      "page",
    )
    fireEvent.click(home)
    await waitFor(() => expect(router.state.location.pathname).toBe("/"))
    expect(within(nav).getByRole("link", { name: "홈" }).getAttribute("aria-current")).toBe("page")
  })
})
