/*
 * 담당: [A] | 책임: 카카오 Handoff 토큰 교환 결과를 웹 상태에 반영한다.
 * PRD: E1 / 스토리 1-4 / 태스크 1-4-3, 1-4-4. API: A05 POST /api/handoff/exchange (openapi, 경로 제안).
 * 구현: 링크의 handoff 값을 읽자마자 주소에서 지우고(J3), 토큰을 본문으로 한 번만 교환한다.
 *   VITE_USE_MOCK_API=false면 공통 Axios로 실제 Backend를 부르고, 아니면 Mock(1회용 토큰)을 쓴다.
 * 완료 기준: 만료·재사용·검증 실패는 구분하지 않는 같은 안내를 보여준다.
 * 제한사항: 토큰을 로그·저장소에 남기지 않는다. 교환 성공은 기기 저장 동의가 아니다.
 */
import { exchangeHandoff as exchangeHandoffMock } from "@/mocks/mock-api"
import { loadApiClient, USE_MOCK_API } from "@/shared/api/data-source"
import type { HandoffPayload } from "@/shared/api/types"

export const HANDOFF_QUERY_KEY = "handoff"

export const exchangeHandoffToken = async (token: string): Promise<HandoffPayload> => {
  if (USE_MOCK_API) return exchangeHandoffMock(token)
  const api = await loadApiClient()
  const response = await api.post<HandoffPayload>("/api/handoff/exchange", { token })
  return response.data
}

// React StrictMode가 effect를 두 번 실행해도 진행 중인 같은 토큰 요청은 하나로 합친다.
// 끝나면 지운다. 같은 링크를 다시 열면 서버에 다시 물어 '이미 사용' 실패를 받아야 하기 때문이다.
const inFlight = new Map<string, Promise<HandoffPayload>>()

export const exchangeHandoffOnce = (token: string): Promise<HandoffPayload> => {
  let pending = inFlight.get(token)
  if (!pending) {
    pending = exchangeHandoffToken(token)
    inFlight.set(token, pending)
    const forget = () => inFlight.delete(token)
    pending.then(forget, forget)
  }
  return pending
}

// 주소에서 handoff 값만 지운 search 문자열을 돌려준다. 다른 query는 남긴다.
export const searchWithoutHandoff = (search: string): string => {
  const params = new URLSearchParams(search)
  params.delete(HANDOFF_QUERY_KEY)
  const rest = params.toString()
  return rest ? `?${rest}` : ""
}
