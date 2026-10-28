/**
 * 담당: A(프론트엔드).
 * 책임: 별도 Origin Render Backend에 요청하는 유일한 Axios REST 인스턴스.
 * 구현할 기능: API Origin, credentials, 공통 취소·타임아웃, 인증 인터셉터 연결.
 * 경계: 채팅 POST+SSE는 fetch/ReadableStream 전용; API URL·HTTP 경로는 API 담당자 소유.
 * 완료 기준: Origin·쿠키·헤더·401 재시도·요청 취소 테스트 통과.
 */
import axios from "axios"
import { AUTH_WIRE, attachAuthSecurity } from "./auth"

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined
if (!apiBaseUrl || !/^https?:\/\//.test(apiBaseUrl)) {
  throw new Error("VITE_API_BASE_URL must be an absolute API origin")
}
export const api = axios.create({
  baseURL: apiBaseUrl,
  withCredentials: true, // Refresh/CSRF 쿠키를 별도 Origin에 전송 시도
  timeout: 30_000, // REST 기본. LLM의 최대 300초와 별개이며 SSE에는 미적용
})

// 모든 REST 요청에 CSRF 헤더·Access Token·401 Refresh 1회 재시도를 적용한다(5-3-1).
attachAuthSecurity(api, AUTH_WIRE)
