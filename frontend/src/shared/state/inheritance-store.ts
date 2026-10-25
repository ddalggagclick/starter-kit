/*
 * 담당: [A] | 책임: 체크리스트 화면의 임시 상태와 selector.
 * PRD: E4 / 스토리 4-2 / 태스크 4-2-1; 화면 연계 2-4-1, 2-4-3, 2-4-4, 2-5-1, 2-5-2; Handoff 반영 1-4-3.
 * 구현: 초기·위험 답변과 절차별 '안내 확인'·'재확인 필요' 상태를 메모리(Zustand)에서만 관리한다.
 * 완료 기준: 답변을 바꾸면 영향받은 위험 질문만 미확인, 이미 확인한 영향 절차만 재확인 배지가 된다.
 * 제한사항: 이 스토어는 메모리만 다룬다. 동의한 경우의 IndexedDB 저장·복원은 features/checklist/checklist-storage.ts가
 *   이 스토어를 구독해 처리한다(4-2-1). 미동의면 새로고침 시 사라진다(D-12).
 *   '안내 확인'은 읽음 표시일 뿐 신고·신청 완료가 아니다(Q71). 체크해도 순서·노출은 바뀌지 않는다(2-5-2).
 */
import { create } from "zustand"
import { RISK_QUESTIONS } from "@/mocks/checklist"
import { PROCEDURE_IDS } from "@/mocks/procedures"
import type { HandoffPayload } from "@/shared/api/types"
import type {
  AnswerChoice,
  InitialAnswers,
  ProcedureId,
  RiskAnswer,
  RiskId,
} from "@/shared/contracts/domain"

// restored: 이 기기에 저장한 답변을 재방문 때 불러온 경우.
export type EntrySource = "direct" | "kakao" | "restored"

export type SavedChecklist = {
  answers: InitialAnswers | null
  riskAnswers: Partial<Record<RiskId, RiskAnswer>>
  procedureStates: Partial<Record<ProcedureId, ProcedureState>>
}
export type ProcedureState = { guidanceRead: boolean; needsRecheck: boolean }

// 초기 답변 항목이 바뀔 때 영향받는 절차·위험 질문.
// 실제 재확인 조건은 B1 ChecklistService(태스크 2-4-2) 소유이며 확정 전이라 화면 확인용 Mock 연결표다.
export const MOCK_ANSWER_IMPACT: Record<
  keyof Pick<InitialAnswers, "relationship" | "deathDate" | "oneStopApplication">,
  { procedureIds: ProcedureId[]; riskIds: RiskId[] }
> = {
  // 번호는 2026-10-22 W-04 원고(D6) 기준. 기한 칸이 사망일과 관련된 절차를 사망일에 연결했다.
  relationship: { procedureIds: ["p02", "p03"], riskIds: [] },
  deathDate: { procedureIds: ["p01", "p03", "p05", "p07"], riskIds: ["self_application"] },
  oneStopApplication: { procedureIds: ["p03", "p04"], riskIds: ["debt"] },
}

const RISK_PROCEDURES: Record<RiskId, ProcedureId[]> = Object.fromEntries(
  RISK_QUESTIONS.map((question) => [question.riskId, question.relatedProcedureIds]),
) as Record<RiskId, ProcedureId[]>

const initialProcedureStates = (): Record<ProcedureId, ProcedureState> =>
  Object.fromEntries(
    PROCEDURE_IDS.map((id) => [id, { guidanceRead: false, needsRecheck: false }]),
  ) as Record<ProcedureId, ProcedureState>

type InheritanceState = {
  answers: InitialAnswers | null
  entrySource: EntrySource | null
  // 답하지 않은(건너뛴) 위험 질문은 키가 없다. '모름'과 '건너뜀'을 구분한다(PRD 1-2).
  riskAnswers: Partial<Record<RiskId, RiskAnswer>>
  procedureStates: Record<ProcedureId, ProcedureState>
  setInitialAnswers: (answers: InitialAnswers, source: EntrySource) => void
  applyHandoff: (payload: HandoffPayload) => void
  restoreSaved: (saved: SavedChecklist) => boolean
  answerRisk: (riskId: RiskId, answer: AnswerChoice) => void
  clearRisk: (riskId: RiskId) => void
  confirmRisk: (riskId: RiskId) => void
  setGuidanceRead: (procedureId: ProcedureId, read: boolean) => void
  reset: () => void
}

const markRecheck = (
  states: Record<ProcedureId, ProcedureState>,
  procedureIds: Iterable<ProcedureId>,
): Record<ProcedureId, ProcedureState> => {
  const next = { ...states }
  for (const id of procedureIds) {
    // 아직 확인하지 않은 절차는 재확인 대상이 아니다(2-4-3: 이미 체크한 절차만).
    if (next[id].guidanceRead) next[id] = { guidanceRead: true, needsRecheck: true }
  }
  return next
}

const changedFields = (before: InitialAnswers, after: InitialAnswers) => {
  const fields: (keyof typeof MOCK_ANSWER_IMPACT)[] = []
  if (before.relationship !== after.relationship) fields.push("relationship")
  if (before.deathDate !== after.deathDate || before.deathDateUnknown !== after.deathDateUnknown) {
    fields.push("deathDate")
  }
  if (before.oneStopApplication !== after.oneStopApplication) fields.push("oneStopApplication")
  return fields
}

export const useInheritanceStore = create<InheritanceState>()((set, get) => ({
  answers: null,
  entrySource: null,
  riskAnswers: {},
  procedureStates: initialProcedureStates(),

  setInitialAnswers: (answers, source) =>
    set((state) => {
      if (!state.answers) return { answers, entrySource: source }
      const fields = changedFields(state.answers, answers)
      const procedureIds = new Set(fields.flatMap((f) => MOCK_ANSWER_IMPACT[f].procedureIds))
      const riskIds = new Set(fields.flatMap((f) => MOCK_ANSWER_IMPACT[f].riskIds))
      const riskAnswers = { ...state.riskAnswers }
      for (const riskId of riskIds) {
        const current = riskAnswers[riskId]
        // 판단이 불명확하면 미확인으로 둔다. 답 자체는 바꾸지 않는다.
        if (current) riskAnswers[riskId] = { ...current, confirmed: false }
      }
      return {
        answers,
        riskAnswers,
        procedureStates: markRecheck(state.procedureStates, procedureIds),
      }
    }),

  // Handoff 성공은 W-02 상태 반영일 뿐 기기 저장 동의가 아니다(1-4-3).
  applyHandoff: (payload) =>
    set({
      answers: {
        relationship: payload.relationship,
        deathDate: payload.deathDate,
        deathDateUnknown: payload.deathDateUnknown,
        oneStopApplication: payload.oneStopApplication,
      },
      entrySource: "kakao",
      // 카카오에서 방금 답한 값이라 확인된 상태로 받는다. 저장 후 재방문(2-4-4)과 다르다.
      riskAnswers: Object.fromEntries(
        (payload.risks ?? []).map((risk) => [
          risk.riskId,
          { riskId: risk.riskId, answer: risk.answer, confirmed: true },
        ]),
      ),
      procedureStates: initialProcedureStates(),
    }),

  // 저장 기록 복원. 이미 메모리에 답이 있으면(카카오 인계·직접 입력 직후) 덮어쓰지 않고 false를 돌려준다.
  // 복원한 위험 답변은 [그대로 맞음]을 누르기 전까지 미확인이다(D-09, 2-4-4).
  restoreSaved: (saved) => {
    if (get().answers || !saved.answers) return false
    set({
      answers: saved.answers,
      entrySource: "restored",
      riskAnswers: Object.fromEntries(
        Object.values(saved.riskAnswers)
          .filter((risk): risk is RiskAnswer => risk !== undefined)
          .map((risk) => [risk.riskId, { ...risk, confirmed: false }]),
      ),
      procedureStates: { ...initialProcedureStates(), ...saved.procedureStates },
    })
    return true
  },

  answerRisk: (riskId, answer) =>
    set((state) => {
      const previous = state.riskAnswers[riskId]
      const changed = previous !== undefined && previous.answer !== answer
      return {
        riskAnswers: { ...state.riskAnswers, [riskId]: { riskId, answer, confirmed: true } },
        procedureStates: changed
          ? markRecheck(state.procedureStates, RISK_PROCEDURES[riskId])
          : state.procedureStates,
      }
    }),

  clearRisk: (riskId) =>
    set((state) => {
      const riskAnswers = { ...state.riskAnswers }
      delete riskAnswers[riskId]
      return { riskAnswers }
    }),

  // [그대로 맞음]을 눌러야만 확인 상태가 된다(2-4-4).
  confirmRisk: (riskId) =>
    set((state) => {
      const current = state.riskAnswers[riskId]
      if (!current) return {}
      return { riskAnswers: { ...state.riskAnswers, [riskId]: { ...current, confirmed: true } } }
    }),

  setGuidanceRead: (procedureId, read) =>
    set((state) => ({
      procedureStates: {
        ...state.procedureStates,
        // 다시 확인하면 재확인 배지가 사라진다. 체크 해제는 두 상태 모두 지운다.
        [procedureId]: { guidanceRead: read, needsRecheck: false },
      },
    })),

  reset: () =>
    set({
      answers: null,
      entrySource: null,
      riskAnswers: {},
      procedureStates: initialProcedureStates(),
    }),
}))

// 안내 확인 수와 재확인 필요 수를 따로 센다(2-5-1). 완료율로 표현하지 않는다.
export const countGuidance = (states: Record<ProcedureId, ProcedureState>) => {
  const values = Object.values(states)
  return {
    read: values.filter((s) => s.guidanceRead && !s.needsRecheck).length,
    recheck: values.filter((s) => s.needsRecheck).length,
    total: values.length,
  }
}
