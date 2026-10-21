/*
 * 담당: [A] | 책임: 클릭 Mock(mock.html) 진입점 — 해시 라우팅·이벤트·Mock API 호출.
 * 근거: PRD 2-1-4·3-1-5, 화면정의서 v1.4 03장 사용자 흐름.
 * 제한사항: 개발 서버 전용 페이지다(npm run build 대상 아님). 실제 앱 라우팅·Axios·use-chat-stream을
 *   대신하지 않는다. 카카오 링크는 실제 `/checklist?handoff=` 대신 `#/handoff?token=`으로 흉내 낸다.
 */
import "./html-mock.css"
import type { AnswerChoice, InitialAnswers, Relationship, RiskId } from "@/shared/contracts/domain"
import { CHAT_INPUT_POLICY, countUnicodeCodePoints } from "@/shared/contracts/ui"
import { type MockAiScenario, mockErrorMessage } from "../ai-stream"
import { type InitialEntryState, RISK_QUESTIONS } from "../checklist"
import { NEW_CHAT_ARCHIVED_COPY } from "../conversations"
import { askAi, exchangeHandoff, login, logout, MockHttpError, signup } from "../mock-api"
import type { ErrorBody, SseEvent } from "../wire-types"
import {
  applyChecklistScenario,
  type ChatMessage,
  createInitialState,
  type MockState,
  setRiskAnswer,
} from "./state"
import {
  type Route,
  renderAuth,
  renderChat,
  renderChecklist,
  renderGuide,
  renderHandoffLoading,
  renderInitialQuestions,
  renderKakao,
  renderLanding,
  renderLayout,
  renderProcedureDetail,
  renderProcedures,
} from "./views"

const root = document.getElementById("mock-root")
if (!root) throw new Error("#mock-root가 없습니다")

let state: MockState = createInitialState()

const parseRoute = (): Route => {
  const raw = window.location.hash.replace(/^#\/?/, "")
  const [path = "", queryString = ""] = raw.split("?")
  const [name = "w-00", param = null] = path.split("/")
  return { name: name || "w-00", param, query: new URLSearchParams(queryString) }
}

const renderBody = (route: Route) => {
  switch (route.name) {
    case "w-00":
      return renderLanding()
    case "w-01":
      return renderInitialQuestions(state)
    case "w-02":
      return renderChecklist(state)
    case "w-03":
      return renderProcedures()
    case "w-04":
      return renderProcedureDetail(state, route.param)
    case "w-05":
      return renderGuide("W-05")
    case "w-06":
      return renderGuide("W-06")
    case "w-07":
      return renderChat(state)
    case "w-09":
      return renderAuth(state)
    case "kakao":
      return renderKakao()
    case "handoff":
      return renderHandoffLoading()
    default:
      return renderLanding()
  }
}

// 다시 그려도 입력 포커스와 커서 위치를 잃지 않게 한다.
const render = () => {
  const active = document.activeElement
  const focusId = active instanceof HTMLElement ? active.id : ""
  const selection =
    active instanceof HTMLTextAreaElement || active instanceof HTMLInputElement
      ? active.selectionStart
      : null
  const route = parseRoute()
  root.innerHTML = renderLayout(state, route, renderBody(route))
  if (focusId) {
    const next = document.getElementById(focusId)
    next?.focus()
    if (selection !== null && next instanceof HTMLTextAreaElement) {
      next.setSelectionRange(selection, selection)
    }
  }
  // 확인창이 뜨면 포커스를 창으로 옮긴다(17장 접근성).
  root.querySelector<HTMLElement>(".modal")?.focus()
}

const go = (to: string) => {
  state.notice = null
  if (window.location.hash === to) render()
  else window.location.hash = to
}

// ── S11 이탈 확인: 저장 안 된 대화 + 사이트 안 이동일 때만 ─────────
const hasUnsavedChat = () =>
  state.chatStorage !== "ready" && (state.messages.length > 0 || state.draft.trim().length > 0)

const navigate = (to: string) => {
  if (parseRoute().name === "w-07" && !to.startsWith("#/w-07") && hasUnsavedChat()) {
    state.modal = { type: "leave", to }
    render()
    return
  }
  go(to)
}

// ── 저장 동의 (Mock: 실제 IndexedDB에 쓰지 않음) ──────────────────
const consent = (scope: "checklist" | "chat", value: "save" | "skip") => {
  if (scope === "checklist") {
    state.checklistConsentDecided = true
    if (value === "save") state.checklistStorage = state.failChecklistStorage ? "failed" : "ready"
  } else {
    state.chatConsentDecided = true
    if (value === "save") state.chatStorage = state.failChatStorage ? "failed" : "ready"
  }
}

// 각 버튼은 자기 데이터만 지운다(D-04). 삭제 뒤 동의 재질문 여부는 검증 필요라 동의는 유지한다.
const deleteData = (scope: "checklist" | "chat") => {
  if (scope === "checklist") {
    state.answers = null
    state.entry = null
    state.riskAnswers = []
    state.itemStates = createInitialState().itemStates
    state.notice = "체크리스트를 삭제했습니다. AI 대화 기록은 그대로입니다."
  } else {
    state.conversations = []
    state.notice = "AI 대화 기록을 삭제했습니다. 체크리스트는 그대로입니다."
  }
}

// ── A05 Handoff ────────────────────────────────────────────────────
const runHandoff = async (route: Route) => {
  const token = route.query.get("token") ?? ""
  const next = route.query.get("next") ?? "w-02"
  // 주소에서 토큰을 지운다(J3). 히스토리에 토큰이 남지 않도록 replaceState를 쓴다.
  history.replaceState(null, "", "#/handoff")
  try {
    const payload = await exchangeHandoff(token)
    state.answers = {
      relationship: payload.relationship,
      deathDate: payload.deathDate,
      deathDateUnknown: payload.deathDateUnknown,
      oneStopApplication: payload.oneStopApplication,
    }
    state.entry = "kakao"
    state.riskAnswers = (payload.risks ?? []).map((risk) => ({ ...risk, confirmed: true }))
    // 교환 성공이 곧 저장 동의는 아니다(PRD 1-4-3).
    history.replaceState(null, "", `#/${next}`)
  } catch {
    // 만료·재사용·검증 실패는 같은 안내 (D-08)
    state.w01Entry = state.hasSavedChecklist ? "E2" : "E1"
    state.answers = null
    history.replaceState(null, "", "#/w-01")
  }
  render()
}

// ── W-01 제출 ──────────────────────────────────────────────────────
const submitInitial = (form: HTMLFormElement) => {
  const data = new FormData(form)
  const relationship = data.get("relationship") as Relationship | null
  const deathDate = (data.get("deathDate") as string) || null
  const deathDateUnknown = data.get("deathDateUnknown") === "on"
  const oneStopApplication = data.get("oneStopApplication") as AnswerChoice | null
  const errors: MockState["w01Errors"] = {}
  if (!relationship) errors.relationship = "관계를 선택해 주세요."
  // 사망일 '모름'과 미입력을 구분한다(PRD 2-1-2).
  if (!deathDate && !deathDateUnknown)
    errors.deathDate = "사망일을 입력하거나 '모름'을 선택해 주세요."
  if (deathDate && deathDateUnknown) errors.deathDate = "날짜와 '모름' 중 하나만 선택해 주세요."
  if (!oneStopApplication) errors.oneStopApplication = "신청 여부를 선택해 주세요."
  state.w01Errors = errors
  if (!relationship || !oneStopApplication || Object.keys(errors).length) {
    render()
    return
  }
  const answers: InitialAnswers = { relationship, deathDate, deathDateUnknown, oneStopApplication }
  state.answers = answers
  if (!state.entry) state.entry = "direct"
  go("#/w-02")
}

// ── W-07 AI 질문 (A08 SSE) ─────────────────────────────────────────
async function* readSse(response: Response): AsyncGenerator<SseEvent> {
  if (!response.body) return
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ""
  for (;;) {
    const { value, done } = await reader.read()
    if (done) return
    buffer += value
    let boundary = buffer.indexOf("\n\n")
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const event = block.match(/^event: (.+)$/m)?.[1]
      const data = block.match(/^data: (.+)$/m)?.[1]
      if (event && data) yield { event, data: JSON.parse(data) } as SseEvent
      boundary = buffer.indexOf("\n\n")
    }
  }
}

const findMessage = (requestId: string) => state.messages.find((m) => m.requestId === requestId)

// 검증된 최종 답변만 자동 타이핑으로 보여준다. 다음 글자·전체 보기 버튼은 두지 않는다.
const typeAnswer = (requestId: string) => {
  const message = findMessage(requestId)
  const full = Array.from(message?.result?.answer ?? "")
  const timer = window.setInterval(() => {
    const current = findMessage(requestId)
    if (!current) {
      window.clearInterval(timer)
      return
    }
    current.typedLength = Math.min(current.typedLength + 2, full.length)
    const element = document.getElementById(`answer-${requestId}`)
    if (element) element.textContent = full.slice(0, current.typedLength).join("")
    if (current.typedLength >= full.length) {
      window.clearInterval(timer)
      render()
    }
  }, 30)
}

const ask = async (question: string) => {
  if (state.activeRequest) return // 한 화면에 활성 요청 1건만 (Q45)
  if (countUnicodeCodePoints(question) > CHAT_INPUT_POLICY.maxQuestionCodePoints) return
  const requestId = crypto.randomUUID()
  const controller = new AbortController()
  const previousQuestions = state.messages
    .map((m) => m.question)
    .slice(-CHAT_INPUT_POLICY.maxPreviousMessages)
  const message: ChatMessage = {
    requestId,
    question,
    status: "pending",
    stage: null,
    result: null,
    error: null,
    typedLength: 0,
    showMoreSources: false,
  }
  state.messages.push(message)
  state.activeRequest = { requestId, controller }
  state.draft = ""
  render()

  const isCurrent = () => state.activeRequest?.requestId === requestId
  try {
    const response = await askAi(
      { question, requestId, previousQuestions },
      {
        scenario: state.aiScenario,
        signal: controller.signal,
        remainingToday: state.accessToken ? null : state.remainingToday - 1,
      },
    )
    if (!response.ok) {
      const body = (await response.json()) as ErrorBody
      if (isCurrent()) message.error = { code: body.code, message: body.message }
    } else {
      for await (const event of readSse(response)) {
        if (!isCurrent()) return // 취소·새 대화 뒤 늦은 응답은 무시 (Q52)
        if (event.event === "status") message.stage = event.data.stage
        if (event.event === "error")
          message.error = { code: event.data.code, message: event.data.message }
        if (event.event === "result") {
          message.result = event.data
          if (event.data.remainingToday !== null) state.remainingToday = event.data.remainingToday
        }
        render()
      }
    }
  } catch {
    if (!isCurrent()) return
    message.error = {
      code: "PROVIDER_UNAVAILABLE",
      message: mockErrorMessage("PROVIDER_UNAVAILABLE"),
    }
  }
  if (!isCurrent()) return
  message.status = "done"
  state.activeRequest = null
  render()
  if (message.result?.state === "answered") typeAnswer(requestId)
}

const cancelActiveRequest = () => {
  state.activeRequest?.controller.abort()
  state.activeRequest = null
}

// 저장 중이면 현재 대화를 이전 대화로 보관한다 (D-01·D-05).
const archiveCurrentChat = () => {
  const answered = state.messages.filter((m) => m.result)
  if (state.chatStorage !== "ready" || answered.length === 0) return
  const now = new Date()
  state.conversations.unshift({
    conversationId: crypto.randomUUID(),
    dateLabel: `${now.getMonth() + 1}/${now.getDate()}`,
    turns: answered.map((m) => ({
      question: m.question,
      result: m.result as NonNullable<ChatMessage["result"]>,
    })),
  })
}

const startNewChat = () => {
  cancelActiveRequest()
  const archived = state.chatStorage === "ready" && state.messages.some((m) => m.result)
  archiveCurrentChat()
  state.messages = []
  state.draft = ""
  state.modal = null
  state.notice = archived ? NEW_CHAT_ARCHIVED_COPY : null
}

// ── W-09 인증 ──────────────────────────────────────────────────────
const submitAuth = async (form: HTMLFormElement) => {
  const data = new FormData(form)
  const email = String(data.get("email") ?? "")
  const password = String(data.get("password") ?? "")
  state.authPending = true
  render()
  try {
    if (state.authTab === "login") {
      const result = await login(email, password)
      state.accessToken = result.accessToken
      state.authMessage = null
      state.authPending = false
      go(state.answers ? "#/w-02" : "#/w-00")
      return
    }
    await signup(email, password)
    state.authMessage = {
      tone: "info",
      text: "가입을 접수했습니다. 이메일 인증 후 로그인할 수 있습니다. (Mock · 실제 메일 발송 없음)",
    }
  } catch (error) {
    const message =
      error instanceof MockHttpError ? error.body.message : "잠시 후 다시 시도해 주세요."
    state.authMessage = { tone: "error", text: message }
  }
  state.authPending = false
  render()
}

// ── 이벤트 위임 ────────────────────────────────────────────────────
root.addEventListener("click", (event) => {
  const target = (event.target as HTMLElement).closest<HTMLElement>("[data-action]")
  if (!target) return
  const { action } = target.dataset
  const d = target.dataset
  switch (action) {
    case "nav":
      navigate(d.to ?? "#/w-00")
      return
    case "consent":
      consent(d.scope as "checklist" | "chat", d.value as "save" | "skip")
      break
    case "delete-data":
      deleteData(d.scope as "checklist" | "chat")
      break
    case "w01-continue-saved":
      applyChecklistScenario(state, "restored")
      state.w01Entry = "E0"
      go("#/w-02")
      return
    case "w01-new":
      state.w01Entry = "E0"
      break
    case "edit-initial":
      go("#/w-01")
      return
    case "confirm-risks":
      state.riskAnswers = state.riskAnswers.map((item) => ({ ...item, confirmed: true }))
      break
    case "edit-risks":
      document.getElementById("risk-section")?.scrollIntoView({ behavior: "smooth" })
      return
    case "risk-answer": {
      const question = RISK_QUESTIONS.find((q) => q.riskId === d.risk)
      if (!question) return
      setRiskAnswer(state, d.risk as RiskId, d.answer as AnswerChoice, question.relatedProcedureIds)
      break
    }
    case "recheck-done":
      state.itemStates = state.itemStates.map((item) =>
        item.procedureId === d.proc ? { ...item, needsRecheck: false, guidanceRead: true } : item,
      )
      break
    case "toggle-section": {
      const key = d.key ?? ""
      if (state.expandedSections.has(key)) state.expandedSections.delete(key)
      else state.expandedSections.add(key)
      break
    }
    case "open-feedback":
      state.modal = { type: "feedback" }
      break
    case "close-modal":
      state.modal = null
      break
    case "example":
      // 예시 질문은 입력칸만 채운다. 제출은 사용자가 한다(PRD 3-1-1).
      state.draft = d.q ?? ""
      break
    case "toggle-sources": {
      const message = findMessage(d.req ?? "")
      if (message) message.showMoreSources = !message.showMoreSources
      break
    }
    case "retry": {
      const message = findMessage(d.req ?? "")
      if (!message || state.activeRequest) return
      state.messages = state.messages.filter((m) => m !== message)
      void ask(message.question)
      return
    }
    case "new-chat":
      // 보내지 않은 입력이 있을 때만 확인 (15장 ② A안, Q60)
      if (state.draft.trim()) state.modal = { type: "newChatConfirm" }
      else startNewChat()
      break
    case "newchat-confirm":
      startNewChat()
      break
    case "toggle-history":
      state.showHistory = !state.showHistory
      break
    case "open-conv": {
      const conversation = state.conversations.find((c) => c.conversationId === d.id)
      if (!conversation) return
      cancelActiveRequest()
      state.messages = conversation.turns.map((turn) => ({
        requestId: crypto.randomUUID(),
        question: turn.question,
        status: "done",
        stage: null,
        result: turn.result,
        error: null,
        typedLength: Array.from(turn.result.answer ?? "").length,
        showMoreSources: false,
      }))
      state.conversations = state.conversations.filter((c) => c.conversationId !== d.id)
      state.showHistory = false
      break
    }
    case "delete-conv":
      state.conversations = state.conversations.filter((c) => c.conversationId !== d.id)
      break
    case "leave-save":
    case "leave-nosave": {
      const to = state.modal?.type === "leave" ? state.modal.to : "#/w-00"
      if (action === "leave-save") {
        state.chatConsentDecided = true
        state.chatStorage = state.failChatStorage ? "failed" : "ready"
        archiveCurrentChat()
      }
      cancelActiveRequest()
      state.messages = []
      state.draft = ""
      state.modal = null
      go(to)
      return
    }
    case "auth-tab":
      state.authTab = d.tab === "signup" ? "signup" : "login"
      state.authMessage = null
      break
    case "logout":
      void logout().then(() => {
        state.accessToken = null
        render()
      })
      return
    case "scenario":
      applyChecklistScenario(state, d.id as "direct" | "kakao" | "restored")
      go("#/w-02")
      return
    case "w01-entry":
      state.w01Entry = d.entry as InitialEntryState
      state.answers = null
      go("#/w-01")
      return
    case "reset":
      cancelActiveRequest()
      state = createInitialState()
      go("#/w-00")
      return
    default:
      return
  }
  render()
})

root.addEventListener("change", (event) => {
  const target = event.target as HTMLInputElement | HTMLSelectElement
  if (target.dataset.action === "toggle-read") {
    const checked = (target as HTMLInputElement).checked
    // 체크해도 순서·노출은 바뀌지 않는다(Q72).
    state.itemStates = state.itemStates.map((item) =>
      item.procedureId === target.dataset.proc ? { ...item, guidanceRead: checked } : item,
    )
    render()
    return
  }
  const key = target.dataset.panel
  if (key === "aiScenario") state.aiScenario = target.value as MockAiScenario
  else if (
    key === "failChecklistStorage" ||
    key === "failChatStorage" ||
    key === "hasSavedChecklist"
  ) {
    state[key] = (target as HTMLInputElement).checked
  } else return
  render()
})

root.addEventListener("input", (event) => {
  const target = event.target as HTMLElement
  if (!(target instanceof HTMLTextAreaElement) || target.id !== "chat-input") return
  state.draft = target.value
  // 입력마다 전체를 다시 그리지 않고 글자 수·제출 버튼만 갱신한다.
  const count = countUnicodeCodePoints(state.draft)
  const over = count > CHAT_INPUT_POLICY.maxQuestionCodePoints
  const counter = document.getElementById("chat-count")
  if (counter) {
    counter.textContent = `${count} / ${CHAT_INPUT_POLICY.maxQuestionCodePoints}자${over ? " · 글자 수를 줄여 주세요" : ""}`
    counter.className = `small ${over ? "error-text" : "muted"}`
  }
  const submit = root.querySelector<HTMLButtonElement>(".chat-form button[type=submit]")
  if (submit) submit.disabled = over || state.activeRequest !== null
})

root.addEventListener("submit", (event) => {
  event.preventDefault()
  const form = event.target as HTMLFormElement
  if (form.dataset.form === "w01") submitInitial(form)
  if (form.dataset.form === "chat" && state.draft.trim()) void ask(state.draft.trim())
  if (form.dataset.form === "auth") void submitAuth(form)
})

document.addEventListener("keydown", (event) => {
  // 확인창 Esc = 취소 (17장 접근성)
  if (event.key === "Escape" && state.modal) {
    state.modal = null
    render()
  }
})

window.addEventListener("hashchange", () => {
  const route = parseRoute()
  if (route.name === "handoff" && route.query.has("token")) void runHandoff(route)
  render()
})

const initialRoute = parseRoute()
if (initialRoute.name === "handoff" && initialRoute.query.has("token"))
  void runHandoff(initialRoute)
render()
