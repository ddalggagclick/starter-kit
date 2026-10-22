/*
 * 담당: [A] | 책임: W-02 진입 시 Handoff 교환 상태를 화면에 알려 준다.
 * PRD: 태스크 1-4-3, 1-4-4 / 화면정의서 v1.4 부록1 E0~E3, D-06·D-08.
 * 구현: 토큰이 있으면 즉시 주소에서 지우고(replace) 교환한다. 성공하면 Zustand에 답을 넣는다.
 * 제한사항: 실패 사유(만료·재사용·없음·네트워크)를 화면에 구분하지 않는다.
 */
import { useEffect, useRef, useState } from "react"
import { useLocation, useNavigate } from "react-router"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { exchangeHandoffOnce, HANDOFF_QUERY_KEY, searchWithoutHandoff } from "./handoff"

export type HandoffStatus = "none" | "exchanging" | "success" | "failed"

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
    exchangeHandoffOnce(token)
      .then((payload) => {
        if (!mounted.current) return
        applyHandoff(payload)
        setStatus("success")
      })
      .catch(() => {
        if (mounted.current) setStatus("failed")
      })
  }, [token, location.pathname, location.search, navigate, applyHandoff])

  return status
}
