// @vitest-environment jsdom
// 삭제·철회 버튼 테스트(4-3-1~4-3-4): 확인창 구분, 취소 시 미실행, 성공 후에만 완료 안내, 실패 시 남은 기록 안내·재시도.
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { StorageControls } from "./storage-controls"

afterEach(cleanup)

const renderControls = (onDelete = vi.fn(async () => true), onRevoke = vi.fn(async () => true)) => {
  render(
    <StorageControls
      available
      itemName="체크리스트 기록"
      deleteLabel="체크리스트 삭제"
      revokeLabel="체크리스트 저장 동의 철회"
      onDelete={onDelete}
      onRevoke={onRevoke}
    />,
  )
  return { onDelete, onRevoke }
}

describe("StorageControls", () => {
  it("삭제 확인창은 동의 유지, 철회 확인창은 동의 해제를 알리고, 취소하면 실행하지 않는다", () => {
    const { onDelete, onRevoke } = renderControls()

    fireEvent.click(screen.getByRole("button", { name: "체크리스트 삭제" }))
    expect(screen.getByRole("dialog").textContent).toMatch(/저장 동의는 유지되어/)
    fireEvent.click(screen.getByRole("button", { name: "취소" }))

    fireEvent.click(screen.getByRole("button", { name: "체크리스트 저장 동의 철회" }))
    expect(screen.getByRole("dialog").textContent).toMatch(/저장 동의를 해제합니다/)
    fireEvent.keyDown(window, { key: "Escape" })

    expect(screen.queryByRole("dialog")).toBeNull()
    expect(onDelete).not.toHaveBeenCalled()
    expect(onRevoke).not.toHaveBeenCalled()
  })

  it("성공하면 그 뒤에만 완료 안내를 보인다", async () => {
    renderControls()

    fireEvent.click(screen.getByRole("button", { name: "체크리스트 삭제" }))
    fireEvent.click(screen.getByRole("button", { name: "삭제: 체크리스트 기록" }))

    expect(
      await screen.findByText(/체크리스트 기록을 삭제했습니다. 저장 동의는 유지됩니다/),
    ).toBeTruthy()
  })

  it("실패하면 완료 안내 없이 남은 기록을 알리고, [다시 시도]로 같은 작업을 다시 한다", async () => {
    const onRevoke = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    renderControls(undefined, onRevoke)

    fireEvent.click(screen.getByRole("button", { name: "체크리스트 저장 동의 철회" }))
    fireEvent.click(screen.getByRole("button", { name: "동의 철회: 체크리스트 기록 삭제" }))

    expect(await screen.findByText(/동의를 철회하지 못했습니다/)).toBeTruthy()
    expect(screen.getByText(/그대로 남아 있고 저장 동의도 바뀌지 않았습니다/)).toBeTruthy()
    expect(screen.queryByText(/철회하고/)).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }))
    expect(
      await screen.findByText(/저장 동의를 철회하고 이 기기의 체크리스트 기록을 삭제했습니다/),
    ).toBeTruthy()
    expect(onRevoke).toHaveBeenCalledTimes(2)
  })
})
