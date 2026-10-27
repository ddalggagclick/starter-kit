// @vitest-environment jsdom
// W-02 저장 동의 띠 화면 테스트(4-1-1, 4-1-2, 4-1-3, D-10). jsdom에는 IndexedDB가 없어 저장 불가 브라우저를 흉내 낸다.
// #197: 동의는 [저장 설정]을 눌러 여는 모달에서 받는다.
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { ChecklistConsentBand } from "./checklist-consent-band"
import { useChecklistStorageStore } from "./checklist-storage"

beforeEach(() => {
  useChecklistStorageStore.setState({ status: "not-consented", declined: false })
})
afterEach(cleanup)

const openSettings = () => fireEvent.click(screen.getByRole("button", { name: "저장 설정" }))

describe("ChecklistConsentBand", () => {
  it("미동의면 '저장 안 됨'과 [저장 설정]만 보이고, 모달에서 정책 확인 체크 전에는 [저장]을 누를 수 없다", () => {
    render(<ChecklistConsentBand />)

    expect(screen.getByText(/저장 안 됨/)).toBeTruthy()
    // 누르기 전에는 모달(정책·저장 버튼)이 없다.
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(screen.queryByRole("button", { name: "저장" })).toBeNull()
    openSettings()
    expect(
      screen.getByRole("dialog", { name: "체크리스트 답을 이 기기에 저장할까요?" }),
    ).toBeTruthy()
    const save = screen.getByRole("button", { name: "저장" }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    fireEvent.click(screen.getByLabelText("저장 정책을 확인했습니다"))
    expect(save.disabled).toBe(false)
  })

  it("[저장 안 함]을 누르면 모달을 닫고 미동의 상태를 그대로 보인다", () => {
    render(<ChecklistConsentBand />)

    openSettings()
    fireEvent.click(screen.getByRole("button", { name: "저장 안 함" }))

    expect(screen.queryByRole("dialog")).toBeNull()
    expect(screen.queryByRole("button", { name: "저장 설정" })).toBeNull()
    expect(screen.getByText(/저장 안 됨/)).toBeTruthy()
  })

  it("저장할 수 없는 브라우저에서 [저장]을 누르면 '저장 중'이 아니라 '저장 불가'를 보인다", async () => {
    render(<ChecklistConsentBand />)

    openSettings()
    fireEvent.click(screen.getByLabelText("저장 정책을 확인했습니다"))
    fireEvent.click(screen.getByRole("button", { name: "저장" }))

    expect(await screen.findByText(/이 브라우저에서는 저장할 수 없습니다/)).toBeTruthy()
    expect(screen.queryByText(/이 기기에 저장 중/)).toBeNull()
  })

  it("저장 중이면 동의 버튼 없이 상태만 보인다", () => {
    useChecklistStorageStore.setState({ status: "ready" })
    render(<ChecklistConsentBand />)

    expect(screen.getByText(/이 기기에 저장 중/)).toBeTruthy()
    expect(screen.queryByRole("button", { name: "저장 설정" })).toBeNull()
  })

  it("Esc로 닫으면 아무것도 고르지 않은 것이라 [저장 설정]이 남고 다시 열 수 있다", () => {
    render(<ChecklistConsentBand />)

    openSettings()
    fireEvent.keyDown(document, { key: "Escape" })

    expect(screen.queryByRole("dialog")).toBeNull()
    expect(useChecklistStorageStore.getState().declined).toBe(false)
    openSettings()
    expect(screen.getByRole("dialog")).toBeTruthy()
  })
})
