/*
 * 담당: [A] | 책임: W-02 진입 시 Handoff 교환 상태를 화면에 알려 준다.
 * PRD: 태스크 1-4-3, 1-4-4 / 화면정의서 v1.4 부록1 E0~E3, D-06·D-08.
 * 구현: 토큰이 있으면 즉시 주소에서 지우고(replace) 교환한다. 성공하면 Zustand에 답을 넣는다.
 *   사용자 지시(2026-10-30): 교환 중에도 진입 선택 창을 띄우므로, 사용자가 교환 중에 다른 화면(AI 등)으로 가도
 *   받은 답은 버리지 않고 넣는다(토큰은 한 번만 쓸 수 있다). "교환 중" 여부는 앱 공용(useHandoffFlight)으로 알려
 *   진입 선택 창·플로팅 [체크리스트]·다시 들어온 체크리스트가 질문 3개 대신 스켈레톤으로 기다리게 한다.
 * 제한사항: 실패 사유(만료·재사용·없음·네트워크)를 화면에 구분하지 않는다.
 */
import { useEffect, useRef, useState } from "react"
import { useLocation, useNavigate } from "react-router"
import { create } from "zustand"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { exchangeHandoffOnce, HANDOFF_QUERY_KEY, searchWithoutHandoff } from "./handoff"

export type HandoffStatus = "none" | "exchanging" | "success" | "failed"

// 앱 공용: 지금 카카오 인계 답을 받는 중인지(메모리, 토큰·답 내용은 담지 않는다).
export const useHandoffFlight = create<{ inFlight: boolean }>(() => ({ inFlight: false }))

export const useHandoff = (): HandoffStatus => {
  const location = useLocation()
  const navigate = useNavigate()
  const applyHandoff = useInheritanceStore((state) => state.applyHandoff)
  const token = new URLSearchParams(location.search).get(HANDOFF_QUERY_KEY)
  const [status, setStatus] = useState<HandoffStatus>(token ? "exchanging" : "none")
  // 주소에서 토큰을 지우면 다시 렌더링되므로, 처리한 토큰과 마운트 여부를 ref로 기억한다.
  const handledToken = useRef<string | null>(null)
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    if (!token || handledToken.current === token) return
    handledToken.current = token
    // 토큰을 주소·방문 기록에 남기지 않는다. 교환 결과를 기다리기 전에 먼저 지운다.
    navigate(
      { pathname: location.pathname, search: searchWithoutHandoff(location.search) },
      { replace: true },
    )
    setStatus("exchanging")
    useHandoffFlight.setState({ inFlight: true })
    exchangeHandoffOnce(token)
      .then((payload) => {
        // 화면을 떠났어도 받은 답은 넣는다(한 번만 쓰는 토큰이라 다시 받을 수 없다).
        applyHandoff(payload)
        if (mounted.current) setStatus("success")
      })
      .catch(() => {
        if (mounted.current) setStatus("failed")
      })
      .finally(() => useHandoffFlight.setState({ inFlight: false }))
  }, [token, location.pathname, location.search, navigate, applyHandoff])

  return status
}
