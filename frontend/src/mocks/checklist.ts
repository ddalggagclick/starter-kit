/*
 * 담당: [A] | 책임: W-01·W-02(R1~R3·P1·C1)·K-01~K-04 표시용 Mock 데이터.
 * 근거: 화면정의서 v1.4 04·05·09·10·15장, 부록1~3, 부록5(COMMON-01·02).
 * 제한사항: 위험 안내 문구는 화면정의서 그림에 나온 문장만 '승인 문구'로 둔다.
 *   문구가 없는 답은 공통 위험 경고만 보여준다(15장 ① A안 확정). 새 안내 문장을 만들지 않는다.
 *   안내·위험 계산 규칙은 서버(ChecklistService) 소유이며 여기서는 화면 확인용 고정값만 둔다.
 */

import type {
  AnswerChoice,
  InitialAnswers,
  ProcedureId,
  Relationship,
  RiskId,
} from "@/shared/contracts/domain"
import type { StorageConsentScope, StorageStatus } from "@/shared/contracts/ui"

// 모든 화면 맨 위 공통 위험 경고 (Q70)
export const COMMON_RISK_WARNING = "기한 · 채무는 공식 자료로 확인하세요."
export const LEGAL_DISCLAIMER = "법률 판단을 대신하지 않습니다"

// W-00 첫 화면 문구 (05장 그림)
export const LANDING_COPY = {
  eyebrow: "가족의 사망 이후, 다음 행동부터",
  title: "무엇부터 해야 할지 함께 확인하세요.",
  description: "한 번에 다 하지 않아도 됩니다.",
  startButton: "상속 절차 시작하기",
} as const

export const RELATIONSHIP_OPTIONS: { value: Relationship; label: string }[] = [
  { value: "spouse", label: "배우자" },
  { value: "descendant", label: "자녀 · 손자녀" },
  { value: "ascendant", label: "부모 · 조부모" },
  { value: "sibling", label: "형제자매" },
  { value: "other", label: "그 밖의 친족" },
  { value: "unknown", label: "모름" },
]

export const ONE_STOP_OPTIONS: { value: AnswerChoice; label: string }[] = [
  { value: "yes", label: "신청함" },
  { value: "no", label: "신청 안 함" },
  { value: "unknown", label: "모름" },
]

export const INITIAL_QUESTION_COPY = {
  relationship: "고인과 어떤 관계인가요?",
  deathDate: "고인의 사망일을 알고 있나요?",
  deathDateUnknownLabel: "모름",
  oneStopApplication: "안심상속 원스톱 서비스를 신청했나요?",
  submitButton: "체크리스트 확인",
} as const

export type RiskQuestion = {
  riskId: RiskId
  // 화면정의서 위험 안내 번호 W01~W03
  guidanceCode: "W01" | "W02" | "W03"
  question: string
  answerLabels: Record<AnswerChoice, string>
  // 문구가 승인된 답만 값이 있다. 없는 답은 공통 위험 경고만 표시한다.
  approvedGuidance: Partial<Record<AnswerChoice, string>>
  // 관련 절차 연결표는 검증 필요(Q126 C). Mock 배정이다.
  // 2026-10-22 W-04 원고 번호(D6)에 맞춤: p04 재산·채무 확인, p05 상속포기·한정승인.
  relatedProcedureIds: ProcedureId[]
}

const PRESENCE_LABELS: Record<AnswerChoice, string> = { yes: "있음", no: "없음", unknown: "모름" }

export const RISK_QUESTIONS: RiskQuestion[] = [
  {
    riskId: "debt",
    guidanceCode: "W01",
    question: "채무 · 보증이 있나요?",
    answerLabels: PRESENCE_LABELS,
    approvedGuidance: {
      yes: "공식 조회 방법을 살펴보고, 채무 부담은 대한법률구조공단에 상담하세요.",
    },
    relatedProcedureIds: ["p04", "p05"],
  },
  {
    riskId: "property_disposal",
    guidanceCode: "W02",
    question: "사망 후 고인의 재산을 처분 · 사용한 적이 있나요?",
    answerLabels: PRESENCE_LABELS,
    approvedGuidance: { yes: "법적 영향은 대한법률구조공단에 상담하세요." },
    relatedProcedureIds: ["p05"],
  },
  {
    riskId: "self_application",
    guidanceCode: "W03",
    question: "상속포기 · 한정승인을 본인이 신청했거나 신청할 예정인가요?",
    answerLabels: { yes: "예", no: "아니요", unknown: "모름" },
    approvedGuidance: { yes: "신청 가능 여부 · 기한은 상황에 따라 다릅니다." },
    relatedProcedureIds: ["p05"],
  },
]

// 승인 문구가 없으면 null — 화면은 공통 위험 경고 + 웹 링크만 표시한다.
export const findRiskGuidance = (riskId: RiskId, answer: AnswerChoice): string | null =>
  RISK_QUESTIONS.find((item) => item.riskId === riskId)?.approvedGuidance[answer] ?? null

// COMMON-01·02 저장 상태 문구. '저장 중'은 실제 저장 성공 때만 쓴다(D-10).
export const STORAGE_STATUS_LABELS: Record<StorageStatus, string> = {
  "not-consented": "미동의 · 저장 안 됨, 새로고침하면 사라집니다",
  ready: "● 이 기기에 저장 중",
  failed: "⚠ 이 브라우저에서는 저장할 수 없습니다",
}

// 동의는 체크리스트(W-02)와 AI 대화(S1)를 따로 받는다(D-03). 두 버튼은 기본 선택 없이 동등하게.
export const CONSENT_COPY: Record<StorageConsentScope, { question: string; note?: string }> = {
  checklist: { question: "체크리스트 답을 이 기기에 저장할까요?" },
  chat: { question: "AI 대화를 이 기기에 저장할까요?", note: "기기를 함께 쓰면 보일 수 있습니다." },
}

export const DELETE_BUTTON_LABELS: Record<StorageConsentScope, string> = {
  checklist: "체크리스트 삭제",
  chat: "대화 기록 삭제",
}

// W-01 진입 상태 E0~E3 (부록1). 링크 실패 사유는 구분하지 않고 같은 문구를 쓴다(D-08).
export type InitialEntryState = "E0" | "E1" | "E2" | "E3"
export const HANDOFF_FAILURE_COPY = "카카오톡 답변을 불러오지 못했습니다"

// 안내 확인(C1)은 읽음 표시일 뿐 신고·신청 완료가 아니다(Q71).
// 서버 itemStates 구조가 미정이라 Mock 전용 형태로 둔다.
export type MockChecklistItemState = {
  procedureId: ProcedureId
  guidanceRead: boolean
  needsRecheck: boolean
}

export type MockRiskAnswerState = { riskId: RiskId; answer: AnswerChoice; confirmed: boolean }

export type MockChecklistScenario = {
  id: "direct" | "kakao" | "restored"
  label: string
  answers: InitialAnswers
  riskAnswers: MockRiskAnswerState[]
  itemStates: MockChecklistItemState[]
  checklistStorage: StorageStatus
  // P1 띠에 쓰는 저장 날짜. restored에서만 있다.
  savedAtLabel?: string
}

const DEFAULT_ANSWERS: InitialAnswers = {
  relationship: "descendant",
  deathDate: "2026-09-30",
  deathDateUnknown: false,
  oneStopApplication: "unknown",
}

const allUnread = (): MockChecklistItemState[] =>
  (["p01", "p02", "p03", "p04", "p05", "p06", "p07", "p08"] as const).map((procedureId) => ({
    procedureId,
    guidanceRead: false,
    needsRecheck: false,
  }))

export const MOCK_CHECKLIST_SCENARIOS: Record<MockChecklistScenario["id"], MockChecklistScenario> =
  {
    // W-00 → W-01 직접 입력 (E0)
    direct: {
      id: "direct",
      label: "웹 직접 방문 (E0)",
      answers: DEFAULT_ANSWERS,
      riskAnswers: [],
      itemStates: allUnread(),
      checklistStorage: "not-consented",
    },
    // 카카오 링크 정상 진입: W-01 생략 + K1 띠 (D-06)
    kakao: {
      id: "kakao",
      label: "카카오 링크 진입 (K1 띠)",
      answers: DEFAULT_ANSWERS,
      riskAnswers: [{ riskId: "property_disposal", answer: "yes", confirmed: true }],
      itemStates: allUnread(),
      checklistStorage: "ready",
    },
    // 며칠 뒤 같은 기기 재방문: 위험 답은 [그대로 맞음] 전까지 미반영 (D-09)
    restored: {
      id: "restored",
      label: "저장 답변 재방문 (P1 띠)",
      savedAtLabel: "10/12",
      answers: DEFAULT_ANSWERS,
      riskAnswers: [{ riskId: "property_disposal", answer: "yes", confirmed: false }],
      itemStates: allUnread().map((item) => {
        if (item.procedureId === "p02") return { ...item, guidanceRead: true }
        if (item.procedureId === "p03") return { ...item, guidanceRead: true, needsRecheck: true }
        return item
      }),
      checklistStorage: "ready",
    },
  }
