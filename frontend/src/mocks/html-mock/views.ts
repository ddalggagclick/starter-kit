/*
 * 담당: [A] | 책임: 클릭 Mock 화면 HTML 문자열 렌더링 (화면정의서 v1.4 화면 ID 기준).
 * 제한사항: 화면 배치 확인용 와이어프레임이다. 정식 React 화면·디자인 시스템을 대신하지 않는다.
 *   모든 화면 맨 위에 공통 위험 경고를 둔다(Q70). 상태는 색만으로 구분하지 않고 문구를 함께 쓴다.
 */

import {
  GUEST_DAILY_LIMIT,
  MOCK_EXAMPLE_QUESTIONS,
  PRIVACY_WARNING,
  SSE_STAGE_LABELS,
  WITHHELD_COPY,
} from "@/shared/content/chat"
import {
  COMMON_RISK_WARNING,
  CONSENT_COPY,
  DELETE_BUTTON_LABELS,
  findRiskGuidance,
  HANDOFF_FAILURE_COPY,
  INITIAL_QUESTION_COPY,
  LANDING_COPY,
  LEGAL_DISCLAIMER,
  ONE_STOP_OPTIONS,
  RELATIONSHIP_OPTIONS,
  RISK_QUESTIONS,
  STORAGE_STATUS_LABELS,
} from "@/shared/content/checklist"
import {
  FEEDBACK_MOCK_COPY,
  INHERITANCE_TAX_GUIDE,
  RELATIONSHIP_GUIDE,
} from "@/shared/content/general-info"
import {
  findProcedureName,
  MOCK_DEADLINE_TAGS,
  MOCK_PROCEDURE_DETAILS,
  MOCK_PROCEDURE_SUMMARIES,
} from "@/shared/content/procedures"
import type { ProcedureId } from "@/shared/contracts/domain"
import { CHAT_INPUT_POLICY, countUnicodeCodePoints } from "@/shared/contracts/ui"
import { MOCK_AI_SCENARIO_LABELS, type MockAiScenario } from "../ai-stream"
import { conversationTitle, EMPTY_CONVERSATIONS_COPY, LEAVE_CONFIRM_COPY } from "../conversations"
import { MOCK_ACCOUNT, MOCK_VALID_HANDOFF_TOKEN } from "../mock-api"
import type { OfficialLink, SseSource } from "../wire-types"
import type { ChatMessage, MockState } from "./state"

export type Route = { name: string; param: string | null; query: URLSearchParams }

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
}
export const esc = (value: string) => value.replace(/[&<>"']/g, (char) => ESCAPES[char] ?? char)

const screenTag = (id: string) => `<span class="screen-id">${esc(id)}</span>`

const externalLink = (link: OfficialLink) =>
  `<a class="ext" href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">${esc(link.title)} ↗</a>`

const navButton = (to: string, label: string, className = "btn") =>
  `<button type="button" class="${className}" data-action="nav" data-to="${esc(to)}">${esc(label)}</button>`

const answerLabel = (value: string, options: { value: string; label: string }[]) =>
  options.find((option) => option.value === value)?.label ?? value

// ── 공통 레이아웃 ───────────────────────────────────────────────────
export const renderLayout = (state: MockState, route: Route, body: string) => `
  <div class="mock-banner" role="note">HTML Mock · 실제 API·DB·AI 연동 아님 · 화면정의서 v1.4 기준</div>
  <header class="top">
    <button type="button" class="logo" data-action="nav" data-to="#/w-00"><span class="logo-mark">길</span>상속 길잡이</button>
    <nav aria-label="주요 메뉴">
      ${navButton(state.answers ? "#/w-02" : "#/w-01", "절차 체크리스트", "link")}
      ${navButton("#/kakao", "카카오톡", "link")}
      ${navButton("#/w-07", "AI 질문", "link")}
      ${
        state.accessToken
          ? `<button type="button" class="link" data-action="logout">로그아웃</button>`
          : navButton("#/w-09", "로그인", "link")
      }
    </nav>
  </header>
  <div class="common-warning" role="note"><strong>주의</strong> ${esc(COMMON_RISK_WARNING)}</div>
  ${state.notice ? `<div class="notice" role="status">${esc(state.notice)}</div>` : ""}
  <main id="screen" data-route="${esc(route.name)}">${body}</main>
  <footer class="foot">
    <span>${esc(LEGAL_DISCLAIMER)}</span>
    ${navButton("#/w-03", "전체 절차", "link")}
    ${navButton("#/w-05", "상속 관계", "link")}
    ${navButton("#/w-06", "상속세", "link")}
    <button type="button" class="link" data-action="open-feedback">${esc(FEEDBACK_MOCK_COPY.button)}</button>
  </footer>
  ${renderModal(state)}
  ${renderPanel(state)}
`

// ── W-00 첫 화면 ────────────────────────────────────────────────────
export const renderLanding = () => `
  <section class="card hero">
    ${screenTag("W-00")}
    <p class="pill">${esc(LEGAL_DISCLAIMER)}</p>
    <p class="muted">${esc(LANDING_COPY.eyebrow)}</p>
    <h1>${esc(LANDING_COPY.title)}</h1>
    <p class="muted">${esc(LANDING_COPY.description)}</p>
    ${navButton("#/w-01", LANDING_COPY.startButton, "btn primary wide")}
  </section>
`

// ── W-01 초기 질문 (E0~E3) ──────────────────────────────────────────
const renderEntryBanner = (state: MockState) => {
  if (state.w01Entry === "E1") {
    return `<div class="alert danger" role="alert">⚠ ${esc(HANDOFF_FAILURE_COPY)}. 처음부터 입력해 주세요.</div>`
  }
  if (state.w01Entry === "E2") {
    return `<div class="alert danger" role="alert">⚠ ${esc(HANDOFF_FAILURE_COPY)}<br/>
      10/12 저장 정보
      <button type="button" class="link" data-action="w01-continue-saved">이어서 보기</button> ·
      <button type="button" class="link" data-action="w01-new">새로 입력</button></div>`
  }
  if (state.w01Entry === "E3") {
    return `<div class="alert" role="note">이 기기에 저장된 정보가 없습니다. 처음부터 입력해 주세요.</div>`
  }
  return ""
}

const fieldError = (state: MockState, key: keyof MockState["w01Errors"]) => {
  const message = state.w01Errors[key]
  return message ? `<p class="field-error" id="err-${key}" role="alert">${esc(message)}</p>` : ""
}

export const renderInitialQuestions = (state: MockState) => {
  const answers = state.answers
  const radio = (
    name: string,
    options: { value: string; label: string }[],
    selected: string | undefined,
  ) =>
    options
      .map(
        (
          option,
        ) => `<label class="choice"><input type="radio" name="${name}" value="${esc(option.value)}"
          ${selected === option.value ? "checked" : ""}/> ${esc(option.label)}</label>`,
      )
      .join("")
  return `
  <section class="card">
    ${screenTag(`W-01 · ${state.w01Entry}`)}
    ${renderEntryBanner(state)}
    <h1>초기 질문 3개</h1>
    <form data-form="w01" novalidate>
      <fieldset aria-describedby="err-relationship">
        <legend>${esc(INITIAL_QUESTION_COPY.relationship)}</legend>
        <div class="choices">${radio("relationship", RELATIONSHIP_OPTIONS, answers?.relationship)}</div>
        ${fieldError(state, "relationship")}
      </fieldset>
      <fieldset aria-describedby="err-deathDate">
        <legend>${esc(INITIAL_QUESTION_COPY.deathDate)}</legend>
        <div class="choices">
          <input type="date" name="deathDate" value="${esc(answers?.deathDate ?? "")}" aria-label="사망일"/>
          <label class="choice"><input type="checkbox" name="deathDateUnknown" ${answers?.deathDateUnknown ? "checked" : ""}/>
            ${esc(INITIAL_QUESTION_COPY.deathDateUnknownLabel)}</label>
        </div>
        ${fieldError(state, "deathDate")}
      </fieldset>
      <fieldset aria-describedby="err-oneStopApplication">
        <legend>${esc(INITIAL_QUESTION_COPY.oneStopApplication)}</legend>
        <div class="choices">${radio("oneStopApplication", ONE_STOP_OPTIONS, answers?.oneStopApplication)}</div>
        ${fieldError(state, "oneStopApplication")}
      </fieldset>
      <p class="muted small">초기 답변은 안내를 고르는 데만 쓰며 법률 판정이 아닙니다.</p>
      <button type="submit" class="btn primary wide">${esc(INITIAL_QUESTION_COPY.submitButton)}</button>
    </form>
  </section>`
}

// ── 저장 상태 띠 (COMMON-01·02) ─────────────────────────────────────
const renderStorageBand = (state: MockState, scope: "checklist" | "chat") => {
  const status = scope === "checklist" ? state.checklistStorage : state.chatStorage
  const decided = scope === "checklist" ? state.checklistConsentDecided : state.chatConsentDecided
  const copy = CONSENT_COPY[scope]
  const consent =
    status === "not-consented" && !decided
      ? `<div class="consent" role="group" aria-label="${esc(copy.question)}">
          <span>${esc(copy.question)} ${copy.note ? `<span class="muted small">${esc(copy.note)}</span>` : ""}</span>
          <span class="consent-buttons">
            <button type="button" class="btn" data-action="consent" data-scope="${scope}" data-value="save">저장</button>
            <button type="button" class="btn" data-action="consent" data-scope="${scope}" data-value="skip">저장 안 함</button>
          </span>
        </div>`
      : ""
  const deleteButton =
    status === "ready"
      ? `<button type="button" class="btn danger-outline small" data-action="delete-data" data-scope="${scope}">${esc(DELETE_BUTTON_LABELS[scope])}</button>`
      : ""
  return `
    <div class="storage-band status-${status}" role="status">
      <span><strong>${scope === "checklist" ? "체크리스트" : "AI 대화"}</strong> · ${esc(STORAGE_STATUS_LABELS[status])}</span>
      ${deleteButton}
    </div>
    ${consent}`
}

// ── W-02 맞춤 체크리스트 ────────────────────────────────────────────
const riskSummary = (state: MockState) =>
  state.riskAnswers
    .map((item) => {
      const question = RISK_QUESTIONS.find((q) => q.riskId === item.riskId)
      if (!question) return ""
      const short =
        question.riskId === "debt"
          ? "채무·보증"
          : question.riskId === "property_disposal"
            ? "재산 처분"
            : "본인 신청"
      return `${short}: ${question.answerLabels[item.answer]}`
    })
    .filter(Boolean)
    .join(" · ")

const renderTopBands = (state: MockState) => {
  const unconfirmed = state.riskAnswers.some((item) => !item.confirmed)
  if (state.entry === "restored" && unconfirmed) {
    // P1: 위험 답은 [그대로 맞음] 전까지 미반영 (D-09)
    return `<div class="band p1" role="group" aria-label="저장 답변 확인">
      ${screenTag("W-02 P1")}
      <p>${esc(state.savedAtLabel ?? "")}에 저장한 답변입니다 · ${esc(riskSummary(state))}</p>
      <p class="muted small">확인 전에는 위험 답을 안내에 반영하지 않습니다.</p>
      <span class="row">
        <button type="button" class="btn primary" data-action="confirm-risks">그대로 맞음</button>
        <button type="button" class="btn" data-action="edit-risks">답변 수정</button>
      </span>
    </div>`
  }
  if (state.entry === "kakao") {
    return `<div class="band k1" role="note">${screenTag("W-02 K1")}
      <strong>카카오톡에서 답한 질문</strong>${state.riskAnswers.length ? ` · ${esc(riskSummary(state))}` : ""}</div>`
  }
  return ""
}

// R3: 확인된 위험 답만 관련 절차 경고에 반영한다.
const riskWarningsFor = (state: MockState, procedureId: ProcedureId) =>
  RISK_QUESTIONS.filter((question) => {
    const answer = state.riskAnswers.find((item) => item.riskId === question.riskId)
    return (
      answer?.confirmed &&
      answer.answer === "yes" &&
      question.relatedProcedureIds.includes(procedureId)
    )
  })

const renderRiskSection = (state: MockState) => `
  <section class="card" id="risk-section" aria-labelledby="risk-title">
    ${screenTag("W-02 R1~R3")}
    <h2 id="risk-title">추가 위험 확인 (선택)</h2>
    <p class="muted small">답하지 않아도 체크리스트를 계속 이용할 수 있습니다.</p>
    ${RISK_QUESTIONS.map((question) => {
      const current = state.riskAnswers.find((item) => item.riskId === question.riskId)
      const shown = current?.confirmed ? current : undefined
      const guidance = shown ? findRiskGuidance(question.riskId, shown.answer) : null
      const buttons = (["yes", "no", "unknown"] as const)
        .map(
          (
            answer,
          ) => `<button type="button" class="chip ${current?.answer === answer ? "selected" : ""}"
            aria-pressed="${current?.answer === answer}" data-action="risk-answer"
            data-risk="${question.riskId}" data-answer="${answer}">${esc(question.answerLabels[answer])}</button>`,
        )
        .join("")
      return `<div class="risk-item">
        <p><strong>${esc(question.question)}</strong> <span class="muted small">${shown ? "응답" : "미응답"}</span></p>
        <div class="row">${buttons}</div>
        ${
          shown
            ? `<div class="alert warn" role="status"><strong>주의</strong> ${esc(guidance ?? COMMON_RISK_WARNING)}
                ${guidance ? "" : `<span class="muted small">(승인 문구 없음 · 공통 경고만 표시)</span>`}</div>
               <p class="small">관련 절차: ${question.relatedProcedureIds
                 .map((id) => navButton(`#/w-04/${id}`, `${findProcedureName(id)} ›`, "link"))
                 .join(" ")}</p>`
            : ""
        }
      </div>`
    }).join("")}
  </section>`

export const renderChecklist = (state: MockState) => {
  const answers = state.answers
  if (!answers) return renderInitialQuestions(state)
  const readCount = state.itemStates.filter((item) => item.guidanceRead).length
  const recheckCount = state.itemStates.filter((item) => item.needsRecheck).length
  const deathLabel = answers.deathDateUnknown ? "모름" : (answers.deathDate ?? "")
  return `
  ${renderTopBands(state)}
  ${renderStorageBand(state, "checklist")}
  <section class="card">
    ${screenTag("W-02")}
    <h1>맞춤 체크리스트</h1>
    <p class="small muted">관계 ${esc(answerLabel(answers.relationship, RELATIONSHIP_OPTIONS))} · 사망일 ${esc(deathLabel)} ·
      안심상속 ${esc(answerLabel(answers.oneStopApplication, ONE_STOP_OPTIONS))}
      <button type="button" class="link" data-action="edit-initial">답변 수정</button></p>
    <p class="small" role="status">안내 확인 ${readCount}개 · 재확인 필요 ${recheckCount}개
      <span class="muted">('안내 확인'은 읽음 표시이며 신고·신청 완료가 아닙니다)</span></p>
    <ol class="procedure-list">
      ${MOCK_PROCEDURE_SUMMARIES.map((procedure) => {
        const item = state.itemStates.find((s) => s.procedureId === procedure.procedureId)
        const tag = MOCK_DEADLINE_TAGS[procedure.procedureId]
        const warnings = riskWarningsFor(state, procedure.procedureId)
        return `<li class="procedure-card">
          <div class="procedure-head">
            ${tag ? `<span class="tag">${esc(tag)}</span>` : ""}
            ${item?.needsRecheck ? `<span class="tag recheck">↻ 재확인 필요</span>` : ""}
          </div>
          <button type="button" class="procedure-title" data-action="nav" data-to="#/w-04/${procedure.procedureId}">
            ${esc(procedure.name)} ›</button>
          <p class="small muted">${esc(procedure.summary)}</p>
          ${warnings
            .map(
              (q) =>
                `<p class="alert warn small">⚠ 위험 안내 · ${esc(findRiskGuidance(q.riskId, "yes") ?? COMMON_RISK_WARNING)}</p>`,
            )
            .join("")}
          <label class="choice small"><input type="checkbox" data-action="toggle-read" data-proc="${procedure.procedureId}"
            ${item?.guidanceRead ? "checked" : ""}/> 안내 확인</label>
        </li>`
      }).join("")}
    </ol>
    <p class="small muted">기한 꼬리표는 예시 문구입니다(검증 필요). 표시 순서는 법적 우선순위가 아닙니다.</p>
  </section>
  ${renderRiskSection(state)}`
}

// ── W-03 일반 절차 탐색 ─────────────────────────────────────────────
export const renderProcedures = () => `
  <section class="card">
    ${screenTag("W-03")}
    <h1>상속 절차 8개 전체</h1>
    <ol class="procedure-list">
      ${MOCK_PROCEDURE_SUMMARIES.map(
        (procedure) => `<li class="procedure-card">
          <button type="button" class="procedure-title" data-action="nav" data-to="#/w-04/${procedure.procedureId}">${esc(procedure.name)} ›</button>
          <p class="small muted">${esc(procedure.summary)}</p></li>`,
      ).join("")}
    </ol>
  </section>`

// ── W-04 절차 상세 (B 접기형) ──────────────────────────────────────
const collapsible = (state: MockState, key: string, title: string, items: string[]) => {
  const open = state.expandedSections.has(key)
  return `<div class="fold">
    <button type="button" class="fold-head" aria-expanded="${open}" aria-controls="fold-${key}"
      data-action="toggle-section" data-key="${key}">${esc(title)} ${items.length}건 ${open ? "▲" : "▼"}</button>
    <ul id="fold-${key}" ${open ? "" : "hidden"}>${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
  </div>`
}

export const renderProcedureDetail = (state: MockState, procedureId: string | null) => {
  const detail = procedureId ? MOCK_PROCEDURE_DETAILS[procedureId as ProcedureId] : undefined
  if (!detail) {
    return `<section class="card">${screenTag("W-04")}<p role="alert">없는 절차입니다.</p>${navButton("#/w-03", "전체 절차 보기")}</section>`
  }
  const item = state.itemStates.find((s) => s.procedureId === detail.procedureId)
  const tag = MOCK_DEADLINE_TAGS[detail.procedureId]
  const warnings = riskWarningsFor(state, detail.procedureId)
  return `
  <section class="card">
    ${screenTag("W-04 · B 접기형")}
    <h1>${esc(findProcedureName(detail.procedureId))} ${tag ? `<span class="tag">${esc(tag)}</span>` : ""}</h1>
    <div class="always action"><strong>바로 할 행동</strong> ${esc(detail.action)}</div>
    <div class="always risk"><strong>기한 · 위험</strong> ${esc(detail.deadline)}<br/>${esc(detail.risk)}
      ${warnings.map((q) => `<br/>⚠ ${esc(findRiskGuidance(q.riskId, "yes") ?? COMMON_RISK_WARNING)}`).join("")}</div>
    <div class="always"><strong>담당 기관</strong> ${esc(detail.agency)}</div>
    <p class="small muted">아래 항목의 '길 때' 접는 기준과 초기 접힘은 미정(S01·M-10)이라 Mock은 모두 접어 둡니다.</p>
    ${collapsible(state, `${detail.procedureId}-documents`, "필요 서류", detail.documents)}
    ${collapsible(state, `${detail.procedureId}-methods`, "방법", detail.methods)}
    ${collapsible(state, `${detail.procedureId}-exceptions`, "예외", detail.exceptions)}
    ${collapsible(state, `${detail.procedureId}-contacts`, "문의처", detail.contacts)}
    <div class="row links"><strong>공식 원문</strong> ${detail.officialLinks.map(externalLink).join(" ")}</div>
    <div class="row links"><strong>함께 확인할 절차</strong>
      ${detail.relatedProcedureIds.map((id) => navButton(`#/w-04/${id}`, findProcedureName(id), "chip")).join("")}</div>
    ${
      item?.needsRecheck
        ? `<button type="button" class="btn primary" data-action="recheck-done" data-proc="${detail.procedureId}">안내를 다시 확인했습니다</button>`
        : ""
    }
    <div class="row">
      ${navButton(state.answers ? "#/w-02" : "#/w-03", "← 목록으로")}
      <button type="button" class="btn" data-action="open-feedback">${esc(FEEDBACK_MOCK_COPY.button)}</button>
    </div>
  </section>`
}

// ── W-05 · W-06 일반 안내 ──────────────────────────────────────────
export const renderGuide = (screenId: "W-05" | "W-06") => {
  const guide = screenId === "W-05" ? RELATIONSHIP_GUIDE : INHERITANCE_TAX_GUIDE
  return `
  <section class="card">
    ${screenTag(screenId)}
    <h1>${esc(guide.title)}</h1>
    <p class="alert" role="note">${esc(guide.notice)}</p>
    ${guide.sections
      .map(
        (section) =>
          `<h2>${esc(section.heading)}</h2><ul>${section.body.map((line) => `<li>${esc(line)}</li>`).join("")}</ul>`,
      )
      .join("")}
    <p class="row links"><strong>공식 출처</strong> ${guide.officialLinks.map(externalLink).join(" ")}</p>
  </section>`
}

// ── W-07 AI 질문 (S1~S11) ──────────────────────────────────────────
// url이 null인 출처(전화 상담 안내 등)는 링크 없이 제목만 보인다.
const sourceItem = (source: SseSource) =>
  `<li>${source.url ? externalLink({ title: source.title, url: source.url }) : esc(source.title)}</li>`

const renderSources = (message: ChatMessage) => {
  const sources = message.result?.sources ?? []
  const first = sources.slice(0, 2)
  const rest = sources.slice(2)
  return `<div class="sources">
    <strong>공식 출처</strong>
    <ul>${first.map(sourceItem).join("")}</ul>
    ${
      rest.length
        ? `<button type="button" class="link" aria-expanded="${message.showMoreSources}" data-action="toggle-sources"
            data-req="${esc(message.requestId)}">추가 출처 보기 ${message.showMoreSources ? "▲" : "▾"}</button>
           ${message.showMoreSources ? `<ul>${rest.map(sourceItem).join("")}</ul>` : ""}`
        : ""
    }
  </div>`
}

const renderMessageBody = (state: MockState, message: ChatMessage) => {
  if (message.status === "pending") {
    // S2: 실제 진행 이벤트를 받았을 때만 단계를 보여준다.
    return `<p class="muted" role="status">${screenTag("S2")} ${
      message.stage ? `${esc(SSE_STAGE_LABELS[message.stage])}…` : "요청을 보내는 중…"
    }</p>`
  }
  if (message.error) {
    const limited =
      message.error.code === "RATE_LIMITED" || message.error.code === "PROVIDER_RATE_LIMIT"
    if (limited) {
      return `<div class="alert danger" role="alert">${screenTag("S9")} ⚠ ${esc(message.error.message)}
        ${
          message.error.code === "RATE_LIMITED" && !state.accessToken
            ? `<p>${navButton("#/w-09", "로그인 · 회원가입", "btn primary")}</p>`
            : `<p class="small">절차 안내는 계속 볼 수 있습니다. ${navButton("#/w-03", "전체 절차 보기", "link")}</p>`
        }</div>`
    }
    return `<div class="alert danger" role="alert">${screenTag("S6")} ⚠ ${esc(message.error.message)}
      <p><button type="button" class="btn" data-action="retry" data-req="${esc(message.requestId)}">다시 시도</button></p></div>`
  }
  const result = message.result
  if (!result) return ""
  if (result.state === "withheld") {
    // S7: 답을 숨기고 판단 유보 (D-13 A). 다시 시도 버튼 없음.
    return `<div class="alert warn" role="status">${screenTag("S7")} ${esc(WITHHELD_COPY.message)}
      <p class="small">${esc(WITHHELD_COPY.agencies)} ${externalLink(WITHHELD_COPY.link)}</p></div>`
  }
  const full = result.answer ?? ""
  const typed = Array.from(full).slice(0, message.typedLength).join("")
  const done = message.typedLength >= Array.from(full).length
  return `<div class="answer">${screenTag("S3")}
    <p id="answer-${esc(message.requestId)}" aria-live="polite">${esc(typed)}</p>
    ${done ? renderSources(message) : ""}</div>`
}

const renderHistory = (state: MockState) => `
  <section class="card" aria-labelledby="history-title">
    ${screenTag("S10")}
    <h2 id="history-title">이전 대화</h2>
    ${
      state.conversations.length
        ? `<ul class="history">${state.conversations
            .map((conversation) => {
              const title = conversationTitle(conversation)
              return `<li><button type="button" class="link" data-action="open-conv" data-id="${esc(conversation.conversationId)}">
                ${esc(conversation.dateLabel)} · ${esc(title)}</button>
                <button type="button" class="btn danger-outline small" aria-label="삭제: ${esc(title)}"
                  data-action="delete-conv" data-id="${esc(conversation.conversationId)}">삭제</button></li>`
            })
            .join("")}</ul>`
        : `<p class="muted">${esc(EMPTY_CONVERSATIONS_COPY)}</p>`
    }
    <button type="button" class="btn danger-outline" data-action="delete-data" data-scope="chat">${esc(DELETE_BUTTON_LABELS.chat)}</button>
  </section>`

export const renderChat = (state: MockState) => {
  const codePoints = countUnicodeCodePoints(state.draft)
  const over = codePoints > CHAT_INPUT_POLICY.maxQuestionCodePoints
  const busy = state.activeRequest !== null
  return `
  ${renderStorageBand(state, "chat")}
  <section class="card chat">
    <div class="row between">
      ${screenTag("W-07 S1")}
      <span class="row">
        ${state.chatStorage === "ready" ? `<button type="button" class="btn small" aria-expanded="${state.showHistory}" data-action="toggle-history">이전 대화 ▾</button>` : ""}
        <button type="button" class="btn small" data-action="new-chat">＋ 새 대화</button>
      </span>
    </div>
    <div class="messages">
      ${
        state.messages.length
          ? state.messages
              .map(
                (message) => `<div class="turn"><p class="bubble user">${esc(message.question)}</p>
                ${renderMessageBody(state, message)}</div>`,
              )
              .join("")
          : `<p class="muted">상속 절차에 대해 궁금한 점을 물어보세요. AI 답변은 공식 출처가 확인된 경우에만 보여드립니다.</p>`
      }
    </div>
    <div class="alert danger privacy" role="note"><strong>${esc(PRIVACY_WARNING)}</strong>
      <span class="small">질문은 답변 생성을 위해 외부 AI 서비스로 전송됩니다. 개인정보 자동 탐지는 하지 않습니다.</span></div>
    <div class="row">${MOCK_EXAMPLE_QUESTIONS.map(
      (question) =>
        `<button type="button" class="chip" data-action="example" data-q="${esc(question)}">${esc(question)}</button>`,
    ).join("")}</div>
    <form data-form="chat" class="chat-form">
      <label for="chat-input" class="sr-only">질문 입력</label>
      <textarea id="chat-input" name="question" rows="2" aria-describedby="chat-count">${esc(state.draft)}</textarea>
      <div class="row between">
        <span id="chat-count" class="small ${over ? "error-text" : "muted"}">${codePoints} / ${CHAT_INPUT_POLICY.maxQuestionCodePoints}자${over ? " · 글자 수를 줄여 주세요" : ""}</span>
        <button type="submit" class="btn primary" ${busy || over ? "disabled" : ""}>${busy ? "처리 중" : "질문 보내기 ↑"}</button>
      </div>
      <p class="small muted">${state.accessToken ? "로그인 상태" : `비로그인 · 오늘 남은 질문 ${state.remainingToday} / ${GUEST_DAILY_LIMIT}회`}</p>
    </form>
  </section>
  ${state.chatStorage === "ready" && state.showHistory ? renderHistory(state) : ""}`
}

// ── W-09 로그인 · 회원가입 ──────────────────────────────────────────
export const renderAuth = (state: MockState) => `
  <section class="card narrow">
    ${screenTag("W-09")}
    <div class="row" role="tablist">
      <button type="button" role="tab" class="chip ${state.authTab === "login" ? "selected" : ""}" aria-selected="${state.authTab === "login"}" data-action="auth-tab" data-tab="login">로그인</button>
      <button type="button" role="tab" class="chip ${state.authTab === "signup" ? "selected" : ""}" aria-selected="${state.authTab === "signup"}" data-action="auth-tab" data-tab="signup">회원가입</button>
    </div>
    ${state.authMessage ? `<p class="alert ${state.authMessage.tone === "error" ? "danger" : ""}" role="alert">${esc(state.authMessage.text)}</p>` : ""}
    <form data-form="auth">
      <label>이메일<input type="email" name="email" autocomplete="username" required/></label>
      <label>비밀번호<input type="password" name="password" autocomplete="${state.authTab === "login" ? "current-password" : "new-password"}" required/></label>
      ${state.authTab === "signup" ? `<p class="small muted">8~64자 영문·숫자 조합</p>` : ""}
      <button type="submit" class="btn primary wide" ${state.authPending ? "disabled" : ""}>${state.authTab === "login" ? "로그인" : "회원가입"}</button>
    </form>
    ${navButton("#/w-02", "로그인 없이 계속하기", "btn wide")}
    <p class="small muted">Mock 계정: ${esc(MOCK_ACCOUNT.email)} / ${esc(MOCK_ACCOUNT.password)}</p>
  </section>`

// ── K-01~K-04 카카오톡 미리보기 ─────────────────────────────────────
const bot = (text: string) => `<p class="k-bubble bot">${text}</p>`
const user = (text: string) => `<p class="k-bubble user">${esc(text)}</p>`

export const renderKakao = () => `
  <p class="muted small">카카오 화면은 김선(C) 담당 스킬 서버가 만듭니다. 여기서는 웹 연결 흐름 확인용 미리보기만 둡니다.</p>
  <div class="kakao-grid">
    <section class="k-screen">${screenTag("K-01")}
      ${bot("고인과 어떤 관계인가요?")}${user("자녀 · 손자녀")}
      ${bot("고인의 사망일을 알고 있나요?")}<p class="row"><span class="chip">날짜 선택</span><span class="chip">모름</span></p>
    </section>
    <section class="k-screen">${screenTag("K-02")}
      ${bot(`<strong>주의</strong> ${esc(COMMON_RISK_WARNING)}`)}
      ${bot(`<strong>우선 확인</strong><br/>상속인 · 재산 · 채무 · 상속포기<br/>
        ${navButton(`#/handoff?token=${MOCK_VALID_HANDOFF_TOKEN}&next=w-02`, "웹 체크리스트에서 보기 ↗", "link")}`)}
      <p class="row"><span class="chip">추가 위험 확인 (선택)</span></p>
    </section>
    <section class="k-screen">${screenTag("K-03")}
      ${bot("사망 후 고인의 재산을 처분 · 사용한 적이 있나요?")}${user("있음")}
      ${bot(`<strong>주의</strong> ${esc(findRiskGuidance("property_disposal", "yes") ?? "")}<br/>
        ${navButton(`#/handoff?token=${MOCK_VALID_HANDOFF_TOKEN}&next=w-02`, "웹 체크리스트에서 확인 ↗", "link")}`)}
    </section>
    <section class="k-screen">${screenTag("K-03·F1")}
      ${user("있음")}
      ${bot(`안내를 불러오지 못했습니다.<br/><strong>주의</strong> ${esc(COMMON_RISK_WARNING)}`)}
      <p class="row"><span class="chip">다시 시도</span>${navButton("#/w-01", "웹에서 시작하기 ↗", "chip")}</p>
    </section>
    <section class="k-screen">${screenTag("K-04")}
      ${bot(`<strong>상속포기 · 한정승인</strong><br/>· 재산 · 채무 조사<br/>· 법원 신고 절차와 기한<br/>
        ${navButton(`#/handoff?token=${MOCK_VALID_HANDOFF_TOKEN}&next=w-04/p04`, "웹에서 서류 · 방법 확인 ↗", "link")}`)}
      ${bot("주의: 신청 가능 여부 · 기한은 상황에 따라 다릅니다.")}
    </section>
    <section class="k-screen">${screenTag("링크 실패")}
      ${bot("만료되었거나 이미 사용한 링크로 열어 봅니다.")}
      ${navButton("#/handoff?token=expired&next=w-02", "만료된 링크로 열기 ↗", "link")}
    </section>
  </div>`

export const renderHandoffLoading = () =>
  `<section class="card"><p role="status">카카오톡 답변을 불러오는 중…</p></section>`

// ── 모달 (W-08 · S8 · S11) ─────────────────────────────────────────
const renderModal = (state: MockState) => {
  const modal = state.modal
  if (!modal) return ""
  let content = ""
  if (modal.type === "feedback") {
    content = `${screenTag("W-08")}<h2 id="modal-title">${esc(FEEDBACK_MOCK_COPY.title)}</h2>
      <p>${esc(FEEDBACK_MOCK_COPY.body)}</p>
      <textarea rows="3" aria-label="오류 내용 (전송되지 않음)" placeholder="입력해도 전송되지 않습니다"></textarea>
      <button type="button" class="btn primary wide" data-action="close-modal">${esc(FEEDBACK_MOCK_COPY.close)}</button>`
  } else if (modal.type === "leave") {
    content = `${screenTag("S11")}<h2 id="modal-title">${esc(LEAVE_CONFIRM_COPY.message)}</h2>
      ${state.chatStorage === "failed" ? "" : `<button type="button" class="btn primary wide" data-action="leave-save">${esc(LEAVE_CONFIRM_COPY.saveAndLeave)}</button>`}
      <button type="button" class="btn wide" data-action="leave-nosave">${esc(LEAVE_CONFIRM_COPY.leaveWithoutSave)}</button>
      <button type="button" class="btn wide" data-action="close-modal">${esc(LEAVE_CONFIRM_COPY.cancel)}</button>`
  } else {
    content = `${screenTag("S8")}<h2 id="modal-title">보내지 않은 입력이 있습니다. 새 대화를 시작할까요?</h2>
      <button type="button" class="btn primary wide" data-action="newchat-confirm">새 대화 시작</button>
      <button type="button" class="btn wide" data-action="close-modal">취소</button>`
  }
  return `<div class="modal-backdrop"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1">${content}</div></div>`
}

// ── Mock 패널 ───────────────────────────────────────────────────────
const renderPanel = (state: MockState) => `
  <details class="panel">
    <summary>Mock 시나리오</summary>
    <label>AI 응답 (W-07)
      <select data-panel="aiScenario">
        ${(Object.keys(MOCK_AI_SCENARIO_LABELS) as MockAiScenario[])
          .map(
            (key) =>
              `<option value="${key}" ${state.aiScenario === key ? "selected" : ""}>${esc(MOCK_AI_SCENARIO_LABELS[key])}</option>`,
          )
          .join("")}
      </select></label>
    <label class="choice"><input type="checkbox" data-panel="failChecklistStorage" ${state.failChecklistStorage ? "checked" : ""}/> 체크리스트 저장 실패 흉내 (D-10)</label>
    <label class="choice"><input type="checkbox" data-panel="failChatStorage" ${state.failChatStorage ? "checked" : ""}/> AI 대화 저장 실패 흉내 (D-10)</label>
    <label class="choice"><input type="checkbox" data-panel="hasSavedChecklist" ${state.hasSavedChecklist ? "checked" : ""}/> 이 기기에 저장 정보 있음 (W-01 E2)</label>
    <p class="small">W-02 진입 시나리오</p>
    <div class="row">
      <button type="button" class="chip" data-action="scenario" data-id="direct">직접 (E0)</button>
      <button type="button" class="chip" data-action="scenario" data-id="kakao">카카오 (K1)</button>
      <button type="button" class="chip" data-action="scenario" data-id="restored">재방문 (P1)</button>
    </div>
    <p class="small">W-01 진입 상태</p>
    <div class="row">
      ${(["E0", "E1", "E2", "E3"] as const).map((entry) => `<button type="button" class="chip" data-action="w01-entry" data-entry="${entry}">${entry}</button>`).join("")}
    </div>
    <button type="button" class="btn small" data-action="reset">전체 초기화</button>
  </details>`
