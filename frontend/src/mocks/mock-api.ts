/*
 * 담당: [A] | 책임: openapi.yaml 0.2.0-draft 경로를 흉내 내는 비동기 Mock API.
 * 구현: 지연·취소(AbortSignal)·HTTP 오류(MockHttpError)를 흉내 낸다. 상태는 모듈 메모리에만 둔다.
 * 제한사항: 공통 Axios 인스턴스(shared/api/client.ts)를 거치지 않는다. 실제 Backend 연동 결과로
 *   보고하지 않는다. 경로가 "제안"인 API(x-path-proposed)는 확정 전이다.
 *   토큰·비밀번호를 브라우저 저장소에 쓰지 않는다.
 */

import {
  MOCK_PROCEDURE_DETAILS,
  MOCK_PROCEDURE_SUMMARIES,
  PROCEDURE_IDS,
} from "@/shared/content/procedures"
import type { ProcedureId } from "@/shared/contracts/domain"
import { passwordPolicyOk } from "@/shared/contracts/password-policy"
import { createMockAskResponse, type MockAskOptions } from "./ai-stream"
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
      // openapi 0.2.1: p01~p08이 아닌 ID는 경로 검증에서 422 VALIDATION_ERROR (404는 만들지 않음).
      throw new MockHttpError(422, { code: "VALIDATION_ERROR", message: "없는 절차입니다." })
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
// 로그인할 수 있는 Mock 계정의 현재 상태. 비밀번호 재설정·탈퇴·재가입·메일 인증이 성공하면 실제로 바뀐다.
// (MOCK_ACCOUNT는 처음 값이다. 인증·재설정 링크 토큰은 이 계정의 것으로 본다.)
const mockAccount = { exists: true, verified: true, password: MOCK_ACCOUNT.password as string }

// H5: 서버와 같은 규칙(코드 포인트 8~64자, 영문·숫자 포함)
const isValidPassword = passwordPolicyOk

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
    // 탈퇴한 Mock 계정 이메일로 다시 가입하면 새 비밀번호로 계정을 되살린다.
    // 실제 Backend처럼 메일 인증 전에는 로그인할 수 없다.
    if (email === MOCK_ACCOUNT.email) {
      mockAccount.exists = true
      mockAccount.verified = false
      mockAccount.password = password
    }
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
    const passwordMatches =
      mockAccount.exists && email === MOCK_ACCOUNT.email && password === mockAccount.password
    // 실제 Backend와 같이 비밀번호가 맞은 뒤에만 미인증 사실을 알린다(가입 여부를 새로 드러내지 않음).
    if (passwordMatches && !mockAccount.verified) {
      throw new MockHttpError(401, {
        code: "UNAUTHENTICATED",
        message: "이메일 인증 후 로그인할 수 있습니다.",
      })
    }
    if (!passwordMatches) {
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

// A12 메일 인증·A15 비밀번호 재설정 링크 토큰. 유효 토큰은 1회만 성공하고, 만료·이미 사용·없는 토큰은 같은 400이다.
export const MOCK_VALID_VERIFY_TOKEN = "mock-verify-valid"
export const MOCK_VALID_RESET_TOKEN = "mock-reset-valid"
const consumedLinkTokens = new Set<string>()
const TOKEN_INVALID = { code: "TOKEN_INVALID", message: "링크가 만료되었거나 이미 사용되었습니다." }

export const verifyEmail = (token: string, options: CallOptions = {}) =>
  respond<{ status: 200 }>(() => {
    if (token !== MOCK_VALID_VERIFY_TOKEN || consumedLinkTokens.has(token)) {
      throw new MockHttpError(400, TOKEN_INVALID)
    }
    consumedLinkTokens.add(token)
    if (mockAccount.exists) mockAccount.verified = true
    return { status: 200 }
  }, options)

export const resetPassword = (token: string, newPassword: string, options: CallOptions = {}) =>
  respond<{ status: 200 }>(() => {
    if (!isValidPassword(newPassword)) {
      throw new MockHttpError(422, {
        code: "VALIDATION_ERROR",
        message: "8~64자 영문·숫자 비밀번호를 확인해 주세요.",
      })
    }
    if (token !== MOCK_VALID_RESET_TOKEN || consumedLinkTokens.has(token) || !mockAccount.exists) {
      throw new MockHttpError(400, TOKEN_INVALID)
    }
    consumedLinkTokens.add(token)
    // 이후 로그인은 새 비밀번호로만 된다.
    mockAccount.password = newPassword
    return { status: 200 }
  }, options)

// A16 탈퇴. 응답 본문 모양은 openapi에 없고 Backend 제안 값을 흉내 낸다.
export const deleteAccount = (password: string, options: CallOptions = {}) =>
  respond<{ account: string; sessions: string; checklist: string }>(() => {
    if (!mockAccount.exists) {
      throw new MockHttpError(401, { code: "UNAUTHENTICATED", message: "UNAUTHENTICATED" })
    }
    if (password !== mockAccount.password) {
      throw new MockHttpError(403, { code: "FORBIDDEN", message: "FORBIDDEN" })
    }
    // 탈퇴하면 로그인할 수 없고 같은 이메일로 다시 가입할 수 있다.
    mockAccount.exists = false
    registeredEmails.delete(MOCK_ACCOUNT.email)
    return { account: "deleted", sessions: "deleted", checklist: "not_stored" }
  }, options)

// ── A17 서버 체크리스트 (x-confirmed: false, 제안) ─────────────────
// 계정마다 따로 보관한다. accessToken 자리에 계정을 구분하는 값(Mock은 계정 ID)을 받는다.
const serverChecklists = new Map<string, ChecklistSaved>()

const requireAccount = (accessToken: string | null): string => {
  if (!accessToken)
    throw new MockHttpError(401, { code: "UNAUTHENTICATED", message: "로그인이 필요합니다." })
  return accessToken
}

export const getMyChecklist = (accessToken: string | null, options: CallOptions = {}) =>
  respond<ChecklistSaved>(() => {
    const saved = serverChecklists.get(requireAccount(accessToken))
    if (!saved?.serverSaveConsent) {
      throw new MockHttpError(403, { code: "FORBIDDEN", message: "서버 저장 동의가 없습니다." })
    }
    return structuredClone(saved)
  }, options)

export const putMyChecklist = (
  accessToken: string | null,
  body: ChecklistSaved,
  options: CallOptions = {},
) =>
  respond<ChecklistSaved>(() => {
    const account = requireAccount(accessToken)
    if (!body.serverSaveConsent) {
      throw new MockHttpError(403, { code: "FORBIDDEN", message: "서버 저장 동의가 없습니다." })
    }
    serverChecklists.set(account, structuredClone(body))
    return structuredClone(body)
  }, options)

// DELETE = 동의 철회 + 서버 체크리스트 삭제
export const deleteMyChecklist = (accessToken: string | null, options: CallOptions = {}) =>
  respond<{ status: 204 }>(() => {
    serverChecklists.delete(requireAccount(accessToken))
    return { status: 204 }
  }, options)

// 테스트·Mock 패널에서 모듈 상태를 처음으로 되돌린다.
export const resetMockApiState = () => {
  consumedHandoffTokens.clear()
  consumedLinkTokens.clear()
  loginFailures = 0
  registeredEmails.clear()
  registeredEmails.add(MOCK_ACCOUNT.email)
  mockAccount.exists = true
  mockAccount.verified = true
  mockAccount.password = MOCK_ACCOUNT.password
  serverChecklists.clear()
}
