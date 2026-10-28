// @vitest-environment jsdom
// 5-1-1: 서버가 422(형식 오류)를 돌려주면 형식·규칙 안내를 보이고 가입 완료로 넘어가지 않는다.
// 화면 검사를 통과한 값이라도 서버가 거부하는 경우를 흉내 내려고 가입 요청만 422로 바꾼다. 실제 Backend 검증이 아니다.
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { createMemoryRouter, RouterProvider } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MockHttpError } from "@/mocks/mock-api"
import { SignupPage } from "./signup-page"

vi.mock("./auth-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./auth-api")>()),
  signupRequest: vi.fn(async () => {
    throw new MockHttpError(422, { code: "VALIDATION_ERROR", message: "VALIDATION_ERROR" })
  }),
}))

afterEach(cleanup)

describe("/signup 서버 422 (5-1-1)", () => {
  it("형식·규칙 안내를 보이고 가입 완료로 넘어가지 않는다", async () => {
    render(
      <RouterProvider
        router={createMemoryRouter([{ path: "/signup", element: <SignupPage /> }], {
          initialEntries: ["/signup"],
        })}
      />,
    )
    fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "new@example.com" } })
    fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "newpass123" } })
    fireEvent.change(screen.getByLabelText("비밀번호 확인"), { target: { value: "newpass123" } })
    fireEvent.click(screen.getByRole("button", { name: "가입하기" }))

    expect(await screen.findByText(/이메일 형식과 비밀번호 규칙/)).toBeTruthy()
    expect(screen.queryByText("인증 메일을 확인해 주세요")).toBeNull()
  })
})
