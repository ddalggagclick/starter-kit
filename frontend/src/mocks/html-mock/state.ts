/*
 * 담당: [A] | 책임: 클릭 Mock(mock.html)의 메모리 상태.
 * 제한사항: 브라우저 저장소(IndexedDB·localStorage)에 쓰지 않는다. '저장 중'은 Mock 패널의
 *   성공/실패 설정을 흉내 낸 표시일 뿐 실제 저장이 아니다. 정식 Zustand/Dexie 상태를 대신하지 않는다.
 */
import type { AnswerChoice, InitialAnswers, RiskId } from "@/shared/contracts/domain"
import type { StorageStatus } from "@/shared/contracts/ui"
import type { MockAiScenario } from "../ai-stream"
import { GUEST_DAILY_LIMIT } from "../ai-stream"
import {
  type InitialEntryState,
  MOCK_CHECKLIST_SCENARIOS,
  type MockChecklistItemState,
  type MockChecklistScenario,
  type MockRiskAnswerState,
} from "../checklist"
import { MOCK_CONVERSATIONS, type MockConversation } from "../conversations"
import type { SseResultEvent, SseStage } from "../wire-types"

export type ChatMessage = {
  requestId: string
  question: string
  status: "pending" | "done"
  stage: SseStage | null
  result: SseResultEvent | null
  error: { code: string; message: string } | null
  // 검증된 최종 답변만 자동 타이핑으로 표시한다. 건너뛰기 버튼은 두지 않는다.
  typedLength: number
  showMoreSources: boolean
}

export type Modal =
  | { type: "feedback" }
  | { type: "leave"; to: string }
  | { type: "newChatConfirm" }
  | null

export type MockState = {
  // 체크리스트
  answers: InitialAnswers | null
  entry: MockChecklistScenario["id"] | null
  riskAnswers: MockRiskAnswerState[]
  itemStates: MockChecklistItemState[]
  checklistStorage: StorageStatus
  checklistConsentDecided: boolean
  savedAtLabel: string | null
  w01Entry: InitialEntryState
  w01Errors: Partial<Record<"relationship" | "deathDate" | "oneStopApplication", string>>
  handoffLoading: boolean
  // W-04 접힘. 펼침 상태는 저장하지 않는다(부록3).
  expandedSections: Set<string>
  // AI 질문
  chatStorage: StorageStatus
  chatConsentDecided: boolean
  messages: ChatMessage[]
  conversations: MockConversation[]
  showHistory: boolean
  draft: string
  activeRequest: { requestId: string; controller: AbortController } | null
  remainingToday: number
  // 인증 — Access 토큰은 메모리에만 둔다.
  accessToken: string | null
  authTab: "login" | "signup"
  authMessage: { tone: "error" | "info"; text: string } | null
  authPending: boolean
  // 공통
  modal: Modal
  notice: string | null
  // Mock 패널 설정
  aiScenario: MockAiScenario
  failChecklistStorage: boolean
  failChatStorage: boolean
  hasSavedChecklist: boolean
}

export const createInitialState = (): MockState => ({
  answers: null,
  entry: null,
  riskAnswers: [],
  itemStates: structuredClone(MOCK_CHECKLIST_SCENARIOS.direct.itemStates),
  checklistStorage: "not-consented",
  checklistConsentDecided: false,
  savedAtLabel: null,
  w01Entry: "E0",
  w01Errors: {},
  handoffLoading: false,
  expandedSections: new Set(),
  chatStorage: "not-consented",
  chatConsentDecided: false,
  messages: [],
  conversations: structuredClone(MOCK_CONVERSATIONS),
  showHistory: false,
  draft: "",
  activeRequest: null,
  remainingToday: GUEST_DAILY_LIMIT,
  accessToken: null,
  authTab: "login",
  authMessage: null,
  authPending: false,
  modal: null,
  notice: null,
  aiScenario: "answered",
  failChecklistStorage: false,
  failChatStorage: false,
  hasSavedChecklist: false,
})

export const applyChecklistScenario = (state: MockState, id: MockChecklistScenario["id"]) => {
  const scenario = MOCK_CHECKLIST_SCENARIOS[id]
  state.answers = structuredClone(scenario.answers)
  state.entry = id
  state.riskAnswers = structuredClone(scenario.riskAnswers)
  state.itemStates = structuredClone(scenario.itemStates)
  state.checklistStorage = scenario.checklistStorage
  state.checklistConsentDecided = scenario.checklistStorage !== "not-consented"
  state.savedAtLabel = scenario.savedAtLabel ?? null
}

export const findRiskAnswer = (state: MockState, riskId: RiskId) =>
  state.riskAnswers.find((item) => item.riskId === riskId)

// 답을 바꾸면 관련 절차 중 이미 '안내 확인'한 것만 재확인 배지를 단다(Q73·E2).
// 관련 절차 연결표는 검증 필요(Q126 C)라 Mock 규칙이다.
export const setRiskAnswer = (
  state: MockState,
  riskId: RiskId,
  answer: AnswerChoice,
  relatedProcedureIds: readonly string[],
) => {
  const previous = findRiskAnswer(state, riskId)
  state.riskAnswers = [
    ...state.riskAnswers.filter((item) => item.riskId !== riskId),
    { riskId, answer, confirmed: true },
  ]
  if (previous && previous.answer !== answer) {
    state.itemStates = state.itemStates.map((item) =>
      item.guidanceRead && relatedProcedureIds.includes(item.procedureId)
        ? { ...item, needsRecheck: true }
        : item,
    )
  }
}
