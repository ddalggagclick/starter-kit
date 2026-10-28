/*
 * 담당: [A] | 책임: Mock A08 응답 시나리오(정상 답변·S6·S7·S9)를 화면 밖에서 정하는 설정.
 * 근거: #205. 지난주 발표용 화면 드롭다운("Mock 시나리오 (발표용)")을 없애면서, 자동 시험이
 *   오류·판단 유보·사용 제한 화면을 계속 확인할 수 있도록 시나리오를 이 설정으로 옮겼다.
 * 구현: 기본값은 정상 답변(answered). 화면에는 바꾸는 수단이 없고, 시험 코드만 setState로 바꾼다.
 * 제한사항: Mock 모드(VITE_USE_MOCK_API=true)에서만 쓰인다. 실제 A08 응답에는 영향이 없다.
 */
import { create } from "zustand"
import type { MockAiScenario } from "./ai-stream"

export const useMockAiScenarioStore = create<{ scenario: MockAiScenario }>(() => ({
  scenario: "answered",
}))
