// @vitest-environment jsdom
// 인증 화면 테스트(jsdom + Mock): 메일 링크 2개(팀원 요청)·가입·재설정 요청·탈퇴. 실제 Backend·메일 수신 검증이 아니다.
// fake-indexeddb/auto를 먼저 불러와 앱의 IndexedDB(탈퇴 후 이 기기 기록 삭제)를 메모리로 쓴다.
import "fake-indexeddb/auto"
import { QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { StrictMode } from "react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { appRoutes, createQueryClient } from "@/app"
import {
  deleteAccount,
  MOCK_ACCOUNT,
  MOCK_VALID_RESET_TOKEN,
  MOCK_VALID_VERIFY_TOKEN,
  resetMockApiState,
} from "@/mocks/mock-api"
import { accessSession } from "@/shared/api/auth"
import type { InitialAnswers } from "@/shared/contracts/domain"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { grantChecklistConsentWithSnapshot } from "@/shared/storage/consent"
import { accountNamespace, inheritanceDb, loadChecklist } from "@/shared/storage/db"
import { useAuthStore } from "./auth-store"
import { readHashToken } from "./link-token"
import { loginFailureMessage } from "./login-page"

const renderAt = (path: string, { strict = false } = {}) => {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  const tree = (
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  render(strict ? <StrictMode>{tree}</StrictMode> : tree)
  return router
}

const type = (label: string | RegExp, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } })

beforeEach(() => {
  resetMockApiState()
  useInheritanceStore.getState().reset()
  useAuthStore.getState().signOut()
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("readHashToken", () => {
  it("#token= 값을 읽고, 없거나 비어 있으면 null이다", () => {
    expect(readHashToken("#token=abc")).toBe("abc")
    expect(readHashToken("")).toBeNull()
    expect(readHashToken("#token=")).toBeNull()
    expect(readHashToken("#other=1")).toBeNull()
  })
})

describe("/auth/verify (5-5-1)", () => {
  it("토큰을 주소에서 지우고, 개발 모드(StrictMode)에서도 한 번만 요청해 인증 완료를 보인다", async () => {
    const router = renderAt(`/auth/verify#token=${MOCK_VALID_VERIFY_TOKEN}`, { strict: true })

    expect(await screen.findByText(/이메일 인증이 끝났습니다/)).toBeTruthy()
    expect(router.state.location.hash).toBe("")
    expect(screen.getByRole("link", { name: "로그인하기" })).toBeTruthy()
  })

  it("이미 쓴 링크와 토큰 없는 링크는 같은 안내와 인증 메일 재전송을 보인다", async () => {
    renderAt(`/auth/verify#token=${MOCK_VALID_VERIFY_TOKEN}`)
    await screen.findByText(/이메일 인증이 끝났습니다/)
    cleanup()

    renderAt(`/auth/verify#token=${MOCK_VALID_VERIFY_TOKEN}`)
    expect(await screen.findByText(/링크가 만료되었거나 이미 사용되었습니다/)).toBeTruthy()
    expect(screen.getByRole("button", { name: "인증 메일 다시 받기" })).toBeTruthy()
    cleanup()

    renderAt("/auth/verify")
    expect(await screen.findByText(/링크가 만료되었거나 이미 사용되었습니다/)).toBeTruthy()
  })

  it("재전송은 가입 여부와 관계없이 같은 접수 안내를 보인다", async () => {
    renderAt("/auth/verify")
    type("이메일", "nobody@example.com")
    fireEvent.click(screen.getByRole("button", { name: "인증 메일 다시 받기" }))
    expect(await screen.findByText(/가입된 이메일이면 인증 메일을 다시 보냈습니다/)).toBeTruthy()
  })
})

describe("/auth/reset (5-5-3, 5-5-5)", () => {
  it("토큰을 지우고, 규칙·확인 불일치는 막고, 맞으면 변경 완료를 보인다", async () => {
    const router = renderAt(`/auth/reset#token=${MOCK_VALID_RESET_TOKEN}`)
    await waitFor(() => expect(router.state.location.hash).toBe(""))

    type("새 비밀번호", "short")
    type("새 비밀번호 확인", "short")
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 변경" }))
    expect(await screen.findAllByText(/8~64자, 영문과 숫자/)).not.toHaveLength(0)

    type("새 비밀번호", "newpass123")
    type("새 비밀번호 확인", "newpass124")
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 변경" }))
    expect(await screen.findByText("비밀번호 확인이 일치하지 않습니다.")).toBeTruthy()

    type("새 비밀번호", "newpass123")
    type("새 비밀번호 확인", "newpass123")
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 변경" }))
    expect(await screen.findByText(/비밀번호를 바꿨습니다/)).toBeTruthy()
  })

  it("만료·이미 사용된 링크는 완료로 보이지 않고 재요청 경로를 보인다", async () => {
    renderAt("/auth/reset#token=expired")
    type("새 비밀번호", "newpass123")
    type("새 비밀번호 확인", "newpass123")
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 변경" }))

    expect(await screen.findByText(/링크가 만료되었거나 이미 사용되었습니다/)).toBeTruthy()
    expect(screen.queryByText(/비밀번호를 바꿨습니다/)).toBeNull()
    expect(screen.getByRole("link", { name: "재설정 메일 다시 받기" }).getAttribute("href")).toBe(
      "/auth/forgot",
    )
  })
})

describe("/signup (5-1-1)", () => {
  it("이미 가입된 이메일은 409 안내를 보이고 가입 완료로 넘어가지 않는다", async () => {
    renderAt("/signup")
    type("이메일", MOCK_ACCOUNT.email)
    type("비밀번호", "newpass123")
    type("비밀번호 확인", "newpass123")
    fireEvent.click(screen.getByRole("button", { name: "가입하기" }))

    expect(await screen.findByText(/이미 가입된 이메일입니다/)).toBeTruthy()
    expect(screen.queryByText("인증 메일을 확인해 주세요")).toBeNull()
  })

  it("가입하면 인증 메일 확인 안내와 재전송을 보인다", async () => {
    renderAt("/signup")
    type("이메일", "new@example.com")
    type("비밀번호", "newpass123")
    type("비밀번호 확인", "newpass123")
    fireEvent.click(screen.getByRole("button", { name: "가입하기" }))

    expect(await screen.findByText("인증 메일을 확인해 주세요")).toBeTruthy()
    expect(screen.getByRole("button", { name: "인증 메일 다시 받기" })).toBeTruthy()
  })
})

describe("/signup 유효성·인증 전 차단 (5-1-1)", () => {
  const submit = () => fireEvent.click(screen.getByRole("button", { name: "가입하기" }))

  it("이메일 형식 오류는 그 칸에 바로 보이고 가입 요청을 보내지 않는다", async () => {
    renderAt("/signup")
    type("이메일", "not-an-email")
    type("비밀번호", "newpass123")
    type("비밀번호 확인", "newpass123")
    submit()

    expect(await screen.findByText("이메일 형식을 확인해 주세요.")).toBeTruthy()
    expect(screen.queryByText("인증 메일을 확인해 주세요")).toBeNull()
    expect(screen.getByLabelText("이메일").getAttribute("aria-invalid")).toBe("true")
  })

  it("비밀번호 규칙 위반과 확인 불일치는 막고 가입 완료로 넘어가지 않는다", async () => {
    renderAt("/signup")
    type("이메일", "new@example.com")
    type("비밀번호", "short")
    type("비밀번호 확인", "short")
    submit()
    expect(screen.queryByText("인증 메일을 확인해 주세요")).toBeNull()
    expect(screen.getByLabelText("비밀번호").getAttribute("aria-invalid")).toBe("true")

    type("비밀번호", "newpass123")
    type("비밀번호 확인", "newpass124")
    submit()
    expect(screen.queryByText("인증 메일을 확인해 주세요")).toBeNull()
    expect(screen.getByLabelText("비밀번호").getAttribute("aria-invalid")).toBe("true")
  })

  it("메일 인증 링크를 확인하는 동안 '인증하는 중'을 보이고, 끝나면 완료로 바뀐다", async () => {
    renderAt(`/auth/verify#token=${MOCK_VALID_VERIFY_TOKEN}`)

    expect(screen.getByRole("status").textContent).toBe("인증하는 중…")
    expect(await screen.findByText(/이메일 인증이 끝났습니다/)).toBeTruthy()
  })

  it("가입 직후에는 로그인 상태가 아니고, 메일 인증 전에는 로그인이 막히며, 인증 뒤에야 로그인된다", async () => {
    // Mock 계정을 탈퇴시켜 같은 이메일로 다시 가입할 수 있게 한다(가입 = 미인증 계정).
    await deleteAccount(MOCK_ACCOUNT.password, { latencyMs: 0 })
    const router = renderAt("/signup")
    type("이메일", MOCK_ACCOUNT.email)
    type("비밀번호", "newpass123")
    type("비밀번호 확인", "newpass123")
    submit()
    expect(await screen.findByText("인증 메일을 확인해 주세요")).toBeTruthy()
    expect(useAuthStore.getState().accountId).toBeNull()

    // 인증 전 로그인 → 막힘
    await act(() => router.navigate("/login"))
    type("이메일", MOCK_ACCOUNT.email)
    type("비밀번호", "newpass123")
    fireEvent.click(within(screen.getByRole("main")).getByRole("button", { name: "로그인" }))
    expect(await screen.findByText("이메일 인증 후 로그인할 수 있습니다.")).toBeTruthy()
    expect(useAuthStore.getState().accountId).toBeNull()

    // 메일 인증 뒤 로그인 → 성공
    await act(() => router.navigate(`/auth/verify#token=${MOCK_VALID_VERIFY_TOKEN}`))
    expect(await screen.findByText(/이메일 인증이 끝났습니다/)).toBeTruthy()
    await act(() => router.navigate("/login"))
    type("이메일", MOCK_ACCOUNT.email)
    type("비밀번호", "newpass123")
    fireEvent.click(within(screen.getByRole("main")).getByRole("button", { name: "로그인" }))
    await waitFor(() => expect(useAuthStore.getState().accountId).not.toBeNull())
  })
})

describe("/auth/forgot (5-5-3)", () => {
  it("가입 여부를 드러내지 않는 같은 접수 안내를 보인다", async () => {
    renderAt("/auth/forgot")
    type("이메일", "nobody@example.com")
    fireEvent.click(screen.getByRole("button", { name: "재설정 메일 받기" }))
    expect(await screen.findByText(/가입된 이메일이면 재설정 링크를 보냈습니다/)).toBeTruthy()
  })
})

describe("로그인 실패 문구", () => {
  it("이메일 미인증 401은 서버 안내 문장을, 그 밖의 401은 같은 문구를 쓴다", () => {
    expect(
      loginFailureMessage({
        status: 401,
        code: "UNAUTHENTICATED",
        message: "이메일 인증 후 로그인할 수 있습니다.",
      }),
    ).toBe("이메일 인증 후 로그인할 수 있습니다.")
    expect(
      loginFailureMessage({ status: 401, code: "UNAUTHENTICATED", message: "UNAUTHENTICATED" }),
    ).toBe("이메일 또는 비밀번호를 확인해 주세요.")
  })
})

describe("/account/delete (5-4-1, 5-4-3)", () => {
  const ACCOUNT = { accountId: `mock:${MOCK_ACCOUNT.email}`, email: MOCK_ACCOUNT.email }
  const NAMESPACE = accountNamespace(ACCOUNT.accountId)
  const ANSWERS: InitialAnswers = {
    relationship: "spouse",
    deathDate: null,
    deathDateUnknown: true,
    oneStopApplication: "no",
  }

  const seedAccountRecord = async () => {
    const result = await grantChecklistConsentWithSnapshot(inheritanceDb, NAMESPACE, {
      answers: ANSWERS,
      riskAnswers: {},
      procedureStates: useInheritanceStore.getState().procedureStates,
    })
    expect(result.ok).toBe(true)
  }

  const submitDelete = (password: string) => {
    type("비밀번호 확인", password)
    fireEvent.click(screen.getByLabelText(/탈퇴하면 계정과/))
    fireEvent.click(screen.getByRole("button", { name: "탈퇴하기" }))
  }

  it("로그인하지 않았으면 탈퇴 대신 로그인을 안내한다", () => {
    renderAt("/account/delete")
    expect(screen.getByText("탈퇴하려면 먼저 로그인해 주세요.")).toBeTruthy()
  })

  it("비밀번호가 틀리면 탈퇴하지 않고 로그인 상태와 기록을 그대로 둔다", async () => {
    await seedAccountRecord()
    useAuthStore.getState().signIn(ACCOUNT)
    renderAt("/account/delete")

    submitDelete("wrong-pass1")

    expect(await screen.findByText("비밀번호가 맞지 않습니다.")).toBeTruthy()
    expect(useAuthStore.getState().accountId).toBe(ACCOUNT.accountId)
    const saved = await loadChecklist(inheritanceDb, NAMESPACE)
    expect(saved.ok && saved.value?.answers).toEqual(ANSWERS)
  })

  it("성공하면 이 기기의 그 계정 기록을 지우고 로그아웃하며 다른 기기·백업 한계를 안내한다", async () => {
    await seedAccountRecord()
    useAuthStore.getState().signIn(ACCOUNT)
    renderAt("/account/delete")

    submitDelete(MOCK_ACCOUNT.password)

    expect(await screen.findByText(/탈퇴했습니다/)).toBeTruthy()
    expect(screen.getByText(/즉시 지워지지 않을 수 있습니다/)).toBeTruthy()
    expect(useAuthStore.getState().accountId).toBeNull()
    expect(await loadChecklist(inheritanceDb, NAMESPACE)).toEqual({ ok: true, value: null })
    expect(await inheritanceDb.consents.where("namespace").equals(NAMESPACE).count()).toBe(0)
  })

  it("탈퇴 뒤 이 기기 체크리스트 화면에 그 계정의 답이 남지 않는다 (5-4-3 잔여 노출)", async () => {
    await seedAccountRecord()
    useAuthStore.getState().signIn(ACCOUNT)
    const router = renderAt("/checklist")
    expect(await screen.findByText(/이 기기에 저장한 답변을 불러왔습니다/)).toBeTruthy()

    await act(() => router.navigate("/account/delete"))
    submitDelete(MOCK_ACCOUNT.password)
    expect(await screen.findByText(/탈퇴했습니다/)).toBeTruthy()

    await act(() => router.navigate("/checklist"))
    expect(screen.getByRole("button", { name: "처음 시작하기" })).toBeTruthy()
    expect(screen.queryByText("내 답변")).toBeNull()
    expect(useInheritanceStore.getState().answers).toBeNull()
  })

  it("다른 기기 기록이 자동으로 지워진다고 안내하지 않는다", async () => {
    useAuthStore.getState().signIn(ACCOUNT)
    renderAt("/account/delete")

    expect(screen.getByText(/자동으로 지워지지 않으니 그 기기에서 직접 삭제해 주세요/)).toBeTruthy()
    expect(screen.queryByText(/다음에 접속할 때 정리/)).toBeNull()
  })

  it("A 탈퇴 처리 중 B로 로그인하면 B는 로그아웃되지 않고 A 기록만 지운다", async () => {
    await seedAccountRecord()
    useAuthStore.getState().signIn(ACCOUNT)
    renderAt("/account/delete")

    submitDelete(MOCK_ACCOUNT.password)
    // 서버 응답(Mock 300ms)을 기다리는 사이 다른 계정 B로 로그인한다.
    const B = { accountId: "user-b", email: "b@example.com" }
    act(() => {
      const epoch = accessSession.begin()
      accessSession.setIfCurrent("b-token", epoch)
      useAuthStore.getState().signIn(B)
    })

    expect(await screen.findByText(/탈퇴했습니다/)).toBeTruthy()
    expect(useAuthStore.getState().accountId).toBe("user-b")
    expect(accessSession.get()).toBe("b-token")
    expect(await loadChecklist(inheritanceDb, NAMESPACE)).toEqual({ ok: true, value: null })
  })

  it("이 기기 기록 삭제가 실패하면 '탈퇴했습니다' 대신 남은 기록을 알리고 재시도할 수 있다", async () => {
    await seedAccountRecord()
    useAuthStore.getState().signIn(ACCOUNT)
    renderAt("/account/delete")
    vi.spyOn(inheritanceDb.consents, "where").mockImplementation(() => {
      throw new Error("삭제 실패")
    })

    submitDelete(MOCK_ACCOUNT.password)

    expect(
      await screen.findByText(/이 기기에 저장된 기록\(체크리스트·AI 대화\)을 지우지 못했습니다/),
    ).toBeTruthy()
    expect(screen.queryByText(/탈퇴했습니다/)).toBeNull()
    // 이 기기 기록을 지우기 전에는 로그아웃하지 않는다(재시도가 그 계정 흐름에 묶여 있어야 함).
    expect(useAuthStore.getState().accountId).toBe(ACCOUNT.accountId)

    vi.restoreAllMocks()
    fireEvent.click(screen.getByRole("button", { name: "이 기기 기록 다시 삭제" }))
    expect(await screen.findByText(/탈퇴했습니다/)).toBeTruthy()
    expect(useAuthStore.getState().accountId).toBeNull()
    expect(await loadChecklist(inheritanceDb, NAMESPACE)).toEqual({ ok: true, value: null })
  })
})
