/*
 * 담당: [A] | 책임: 화면 위에 여는 창(모달·메뉴 서랍) 중 지금 열린 것 하나를 기억하는 임시 UI 상태.
 * 근거: #227 새 시안(https://claude.ai/artifact/NgrnTfYvGvuGj5PYWnJcfu) — 전체 절차·상속 관계·상속세·시작 질문·로그인 등은
 *   페이지 이동 없이 지금 화면 위 모달로 열고, 좁은 화면 메뉴는 왼쪽 서랍으로 연다.
 * 구현: 사이드바·버튼이 open(이름)을 부르고, 앱 레이아웃이 이름에 맞는 창을 그린다. 한 번에 하나만 연다.
 *   InOverlayContext: 기존 화면 부품(로그인·질문 3개 등)이 모달 안에서 그려질 때 true다. 부품은 이 값을 보고
 *   "다른 화면으로 이동" 대신 "모달 닫기·다른 모달로 바꾸기"를 한다(같은 화면에 머물러 대화가 끊기지 않게).
 * 제한사항: 저장하지 않는다(새로고침하면 닫힌다). 개인정보·대화 내용은 담지 않는다.
 */
import { createContext, useContext } from "react"
import { create } from "zustand"

export type OverlayName =
  | "steps"
  | "relation"
  | "tax"
  | "start"
  | "menu"
  | "login"
  | "signup"
  | "forgot"
  | "account-delete"
  | "entry"

type OverlayState = {
  current: OverlayName | null
  open: (name: OverlayName) => void
  close: () => void
}

export const useOverlayStore = create<OverlayState>((set) => ({
  current: null,
  open: (name) => set({ current: name }),
  close: () => set({ current: null }),
}))

export const InOverlayContext = createContext(false)

// 지금 부품이 모달 안에서 그려지는지
export const useInOverlay = () => useContext(InOverlayContext)
