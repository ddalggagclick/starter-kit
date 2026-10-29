// @vitest-environment jsdom
// W-02 저장 동의 띠 화면 테스트(4-1-1, 4-1-2, 4-1-3, D-10). jsdom에는 IndexedDB가 없어 저장 불가 브라우저를 흉내 낸다.
// #197: 동의는 모달에서 받는다. #227 최신 시안: 화면에는 저장 상태 칸 + [저장]만 두고, 저장 중이면 [저장] 모달에서 철회한다.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ChecklistConsentBand } from "./checklist-consent-band"
import { useChecklistStorageStore } from "./checklist-storage"

beforeEach(() => {
  useChecklistStorageStore.setState({ status: "not-consented", declined: false })
})
afterEach(cleanup)

// 화면의 [저장](모달을 여는 버튼). 모달 안 [저장]과 구분하려고 띠 안에서 찾는다.
const band = () => screen.getByRole("region", { name: "체크리스트 저장" })
const openSettings = () =>
  fireEvent.click(within(band()).getAllByRole("button", { name: "저장" })[0])

describe("ChecklistConsentBand", () => {
  it("미동의면 점선 '저장 안 됨' 칸과 [저장]만 보이고, 모달에서 정책 확인 체크 전에는 [저장]을 누를 수 없다", () => {
    render(<ChecklistConsentBand />)

    expect(screen.getByText(/저장 안 됨/, { selector: "[role=status]" }).className).toContain(
      "border-dashed",
    )
    // 누르기 전에는 모달(정책·저장 버튼)이 없다.
    expect(screen.queryByRole("dialog")).toBeNull()
    openSettings()
    const dialog = screen.getByRole("dialog", { name: "체크리스트 답을 이 기기에 저장할까요?" })
    const save = within(dialog).getByRole("button", { name: "저장" }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
    fireEvent.click(within(dialog).getByLabelText("저장 정책을 확인했습니다"))
    expect(save.disabled).toBe(false)
  })

  it("[저장 안 함]을 누르면 모달을 닫고 미동의 상태를 그대로 보이며, [저장]으로 다시 고를 수 있다", () => {
    render(<ChecklistConsentBand />)

    openSettings()
    fireEvent.click(screen.getByRole("button", { name: "저장 안 함" }))

    expect(screen.queryByRole("dialog")).toBeNull()
    expect(screen.getByText(/저장 안 됨/)).toBeTruthy()
    openSettings()
    expect(screen.getByRole("dialog")).toBeTruthy()
  })

  it("저장할 수 없는 브라우저에서 [저장]을 누르면 '기기 저장'이 아니라 '저장 불가'를 보인다", async () => {
    render(<ChecklistConsentBand />)

    openSettings()
    const dialog = screen.getByRole("dialog")
    fireEvent.click(within(dialog).getByLabelText("저장 정책을 확인했습니다"))
    fireEvent.click(within(dialog).getByRole("button", { name: "저장" }))

    expect(await screen.findByText(/이 브라우저에서는 저장할 수 없습니다/)).toBeTruthy()
    expect(screen.queryByText("기기 저장")).toBeNull()
  })

  it("저장 중이면 초록 ✓ '기기 저장'을 보이고, [저장] 모달의 [저장 동의 철회]는 모달을 닫고 철회를 요청한다", () => {
    useChecklistStorageStore.setState({ status: "ready" })
    const onRevoke = vi.fn()
    render(<ChecklistConsentBand onRevoke={onRevoke} />)

    const chip = screen.getByText("기기 저장", { selector: "[role=status]" })
    expect(chip.className).toContain("bg-success")
    expect(chip.textContent).toBe("체크리스트 기기 저장")
    openSettings()
    const dialog = screen.getByRole("dialog", { name: "체크리스트 저장" })
    fireEvent.click(within(dialog).getByRole("button", { name: "저장 동의 철회" }))

    expect(screen.queryByRole("dialog")).toBeNull()
    expect(onRevoke).toHaveBeenCalledTimes(1)
  })

  it("Esc로 닫으면 아무것도 고르지 않은 것이라 [저장]이 남고 다시 열 수 있다", () => {
    render(<ChecklistConsentBand />)

    openSettings()
    fireEvent.keyDown(document, { key: "Escape" })

    expect(screen.queryByRole("dialog")).toBeNull()
    expect(useChecklistStorageStore.getState().declined).toBe(false)
    openSettings()
    expect(screen.getByRole("dialog")).toBeTruthy()
  })
})
