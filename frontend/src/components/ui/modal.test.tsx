// @vitest-environment jsdom
// 공통 모달 테스트(#197, 디자인 시스템 7.4·9장): 이름 연결, 열 때 초점 이동, Tab 가두기, Esc·바깥 누르기 닫기, 닫은 뒤 초점 돌려주기.
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { Modal } from "./modal"

afterEach(cleanup)

// 실제 쓰임처럼 부모가 열림 상태를 관리하는 화면
function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false)
  const close = () => {
    onClose()
    setOpen(false)
  }
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        열기
      </button>
      {open && (
        <Modal onClose={close}>
          <Modal.Header title="저장할까요?" subtitle="부제" />
          <Modal.Body>
            <input aria-label="확인" type="checkbox" />
          </Modal.Body>
          <Modal.Actions>
            <button type="button">첫째</button>
            <button type="button">마지막</button>
          </Modal.Actions>
        </Modal>
      )}
    </>
  )
}

const open = () => {
  const opener = screen.getByRole("button", { name: "열기" })
  opener.focus()
  fireEvent.click(opener)
  return opener
}

describe("Modal", () => {
  it("제목을 대화상자 이름으로 읽고, 열리면 모달 안 첫 요소로 초점을 옮긴다", () => {
    render(<Harness />)
    open()

    const dialog = screen.getByRole("dialog", { name: "저장할까요?" })
    expect(dialog.getAttribute("aria-modal")).toBe("true")
    expect(document.activeElement).toBe(screen.getByLabelText("확인"))
  })

  it("Tab·Shift+Tab은 모달 안에서만 돈다", () => {
    render(<Harness />)
    open()

    screen.getByRole("button", { name: "마지막" }).focus()
    fireEvent.keyDown(document, { key: "Tab" })
    expect(document.activeElement).toBe(screen.getByLabelText("확인"))

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true })
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "마지막" }))
  })

  it("Esc로 닫고, 닫히면 모달을 열었던 버튼으로 초점을 돌려준다", () => {
    const onClose = vi.fn()
    render(<Harness onClose={onClose} />)
    const opener = open()

    fireEvent.keyDown(document, { key: "Escape" })

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("dialog")).toBeNull()
    expect(document.activeElement).toBe(opener)
  })

  it("바깥(어두운 배경)을 누르면 닫히고, 모달 안을 누르면 닫히지 않는다", () => {
    const onClose = vi.fn()
    render(<Harness onClose={onClose} />)
    open()

    const dialog = screen.getByRole("dialog")
    fireEvent.click(dialog)
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.click(dialog.parentElement as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("dialog")).toBeNull()
  })
})
