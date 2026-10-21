/*
 * 담당: [A] | 책임: openapi.yaml 0.2.0-draft 경로를 흉내 내는 비동기 Mock API.
 * 구현: 지연·취소(AbortSignal)·HTTP 오류(MockHttpError)를 흉내 낸다. 상태는 모듈 메모리에만 둔다.
 * 제한사항: 공통 Axios 인스턴스(shared/api/client.ts)를 거치지 않는다. 실제 Backend 연동 결과로
 *   보고하지 않는다. 경로가 "제안"인 API(x-path-proposed)는 확정 전이다.
 *   토큰·비밀번호를 브라우저 저장소에 쓰지 않는다.
 */
import type { ProcedureId } from "@/shared/contracts/domain"
import { createMockAskResponse, type MockAskOptions } from "./ai-stream"
import { MOCK_PROCEDURE_DETAILS, MOCK_PROCEDURE_SUMMARIES, PROCEDURE_IDS } from "./procedures"
import type {
  AskAiRequest,
  ChecklistSaved,
  ErrorBody,
  HandoffPayload,
  LoginResponse,
  ProcedureDetail,
  ProcedureListResponse,
} from "./wire-types"

export class MockHttpError extends Error {
  constructor(
    readonly status: number,
    readonly body: ErrorBody,
  ) {
    super(`${status} ${body.code}`)
    this.name = "MockHttpError"
  }
}

export const MOCK_LATENCY_MS = 300

const delay = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason)
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer)
        reject(signal.reason)
      },
      { once: true },
    )
  })

type CallOptions = { signal?: AbortSignal; latencyMs?: number }

const respond = async <T>(value: () => T, { signal, latencyMs = MOCK_LATENCY_MS }: CallOptions) => {
  await delay(latencyMs, signal)
  return value()
}

// ── A05 Handoff 교환 ───────────────────────────────────────────────
// 유효 토큰은 1회만 성공한다. 만료·이미 사용·없는 토큰은 같은 400 응답이다(D-08).
export const MOCK_VALID_HANDOFF_TOKEN = "mock-handoff-valid"
export const MOCK_HANDOFF_PAYLOAD: HandoffPayload = {
  relationship: "descendant",
  deathDate: "2026-09-30",
  deathDateUnknown: false,
  oneStopApplication: "unknown",
  risks: [{ riskId: "property_disposal", answer: "yes" }],
}
const consumedHandoffTokens = new Set<string>()

export const exchangeHandoff = (token: string, options: CallOptions = {}) =>
  respond<HandoffPayload>(() => {
    if (token !== MOCK_VALID_HANDOFF_TOKEN || consumedHandoffTokens.has(token)) {
      throw new MockHttpError(400, {
        code: "HANDOFF_INVALID",
        message: "연결이 만료되었거나 이미 사용되었습니다.",
      })
    }
    consumedHandoffTokens.add(token)
    return structuredClone(MOCK_HANDOFF_PAYLOAD)
  }, options)

// ── A07 절차 ───────────────────────────────────────────────────────
export const listProcedures = (options: CallOptions = {}) =>
  respond<ProcedureListResponse>(
    () => ({ procedures: structuredClone(MOCK_PROCEDURE_SUMMARIES) }),
    options,
  )

const isProcedureId = (value: string): value is ProcedureId =>
  (PROCEDURE_IDS as readonly string[]).includes(value)

export const getProcedure = (procedureId: string, options: CallOptions = {}) =>
  respond<ProcedureDetail>(() => {
    if (!isProcedureId(procedureId)) {
      // 404 코드 이름은 팀 오류 목록에 없어 제안 상태다.
      throw new MockHttpError(404, { code: "NOT_FOUND", message: "없는 절차입니다." })
    }
    return structuredClone(MOCK_PROCEDURE_DETAILS[procedureId])
  }, options)

// ── A08 AI 질문 (SSE) ──────────────────────────────────────────────
export const askAi = (request: AskAiRequest, options: MockAskOptions) =>
  createMockAskResponse(request, options)

// ── A11~A15 인증 ───────────────────────────────────────────────────
export const MOCK_ACCOUNT = { email: "demo@example.com", password: "mockpass1" } as const
const LOGIN_FAILURE_LIMIT = 5
let loginFailures = 0
const registeredEmails = new Set<string>([MOCK_ACCOUNT.email])

// H5: 8~64자 영문·숫자 조합
const isValidPassword = (password: string) =>
  password.length >= 8 && password.length <= 64 && /[A-Za-z]/.test(password) && /\d/.test(password)

const isEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)

export const signup = (email: string, password: string, options: CallOptions = {}) =>
  respond<{ status: 201 }>(() => {
    if (!isEmail(email) || !isValidPassword(password)) {
      throw new MockHttpError(422, {
        code: "VALIDATION_ERROR",
        message: "이메일 형식과 8~64자 영문·숫자 비밀번호를 확인해 주세요.",
      })
    }
    if (registeredEmails.has(email)) {
      // 409 코드 이름은 팀 오류 목록에 없어 제안 상태다.
      throw new MockHttpError(409, { code: "EMAIL_TAKEN", message: "이미 가입된 이메일입니다." })
    }
    registeredEmails.add(email)
    return { status: 201 }
  }, options)

export const login = (email: string, password: string, options: CallOptions = {}) =>
  respond<LoginResponse>(() => {
    if (loginFailures >= LOGIN_FAILURE_LIMIT) {
      throw new MockHttpError(429, {
        code: "RATE_LIMITED",
        message: "로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.",
      })
    }
    if (email !== MOCK_ACCOUNT.email || password !== MOCK_ACCOUNT.password) {
      loginFailures += 1
      // 실패 사유를 구분하지 않고 같은 문구로 안내한다(W-09).
      throw new MockHttpError(401, {
        code: "UNAUTHENTICATED",
        message: "이메일 또는 비밀번호를 확인해 주세요.",
      })
    }
    loginFailures = 0
    return { accessToken: "mock-access-token", expiresIn: 900 }
  }, options)

export const logout = (options: CallOptions = {}) =>
  respond<{ status: 204 }>(() => ({ status: 204 }), options)

// 가입 여부를 알리지 않고 항상 202
export const resendVerificationEmail = (_email: string, options: CallOptions = {}) =>
  respond<{ status: 202 }>(() => ({ status: 202 }), options)
export const requestPasswordReset = (_email: string, options: CallOptions = {}) =>
  respond<{ status: 202 }>(() => ({ status: 202 }), options)

// ── A17 서버 체크리스트 (x-status: 제안) ───────────────────────────
let serverChecklist: ChecklistSaved | null = null

export const getMyChecklist = (accessToken: string | null, options: CallOptions = {}) =>
  respond<ChecklistSaved>(() => {
    if (!accessToken)
      throw new MockHttpError(401, { code: "UNAUTHENTICATED", message: "로그인이 필요합니다." })
    if (!serverChecklist?.serverSaveConsent) {
      throw new MockHttpError(403, { code: "FORBIDDEN", message: "서버 저장 동의가 없습니다." })
    }
    return structuredClone(serverChecklist)
  }, options)

export const putMyChecklist = (
  accessToken: string | null,
  body: ChecklistSaved,
  options: CallOptions = {},
) =>
  respond<ChecklistSaved>(() => {
    if (!accessToken)
      throw new MockHttpError(401, { code: "UNAUTHENTICATED", message: "로그인이 필요합니다." })
    if (!body.serverSaveConsent) {
      throw new MockHttpError(403, { code: "FORBIDDEN", message: "서버 저장 동의가 없습니다." })
    }
    serverChecklist = structuredClone(body)
    return structuredClone(serverChecklist)
  }, options)

// DELETE = 동의 철회 + 서버 체크리스트 삭제
export const deleteMyChecklist = (accessToken: string | null, options: CallOptions = {}) =>
  respond<{ status: 204 }>(() => {
    if (!accessToken)
      throw new MockHttpError(401, { code: "UNAUTHENTICATED", message: "로그인이 필요합니다." })
    serverChecklist = null
    return { status: 204 }
  }, options)

// 테스트·Mock 패널에서 모듈 상태를 처음으로 되돌린다.
export const resetMockApiState = () => {
  consumedHandoffTokens.clear()
  loginFailures = 0
  registeredEmails.clear()
  registeredEmails.add(MOCK_ACCOUNT.email)
  serverChecklist = null
}
