/*
 * 담당: [A] | 책임: Axios·Mock·fetch 오류를 화면이 쓰는 한 가지 모양으로 바꾼다.
 * PRD: E7 / 태스크 7-1-3, 7-2-2(재시도 가능 오류 구분의 준비).
 * 구현: openapi Error {code, message}와 FastAPI HTTPException 기본 모양 {detail: {code, message}}를 모두 읽는다.
 * 제한사항: 오류 원문·토큰을 로그로 남기지 않는다. 코드 이름은 core/errors.py 기준이며 새 코드를 만들지 않는다.
 */
import { MockHttpError } from "@/mocks/mock-api"

export type ApiFailure = {
  // 0은 네트워크 실패·취소 등 HTTP 응답이 없는 경우다.
  status: number
  code: string | null
  message: string | null
}

const readBody = (body: unknown): { code: string | null; message: string | null } => {
  if (!body || typeof body !== "object") return { code: null, message: null }
  const record = body as Record<string, unknown>
  const inner =
    record.detail && typeof record.detail === "object"
      ? (record.detail as Record<string, unknown>)
      : record
  return {
    code: typeof inner.code === "string" ? inner.code : null,
    message: typeof inner.message === "string" ? inner.message : null,
  }
}

export const toApiFailure = (error: unknown): ApiFailure => {
  if (error instanceof MockHttpError) {
    return { status: error.status, code: error.body.code, message: error.body.message }
  }
  const axiosLike = error as { response?: { status?: number; data?: unknown } }
  if (axiosLike?.response?.status) {
    return { status: axiosLike.response.status, ...readBody(axiosLike.response.data) }
  }
  return { status: 0, code: null, message: null }
}

export const readErrorJson = async (response: Response): Promise<ApiFailure> => {
  try {
    return { status: response.status, ...readBody(await response.json()) }
  } catch {
    return { status: response.status, code: null, message: null }
  }
}
