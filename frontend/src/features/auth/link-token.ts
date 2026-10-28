/*
 * 담당: [A] | 책임: 메일 링크(/auth/verify, /auth/reset)의 #token= 값을 읽고 주소에서 지운다.
 * 요청: 팀원 제안 — 토큰은 서버 로그에 남지 않도록 ?가 아니라 # 뒤에 둔다.
 * 구현: 화면이 처음 열릴 때 한 번 읽어 메모리에만 두고, 바로 주소에서 #을 지워 방문 기록·화면 공유에 남기지 않는다.
 * 제한사항: 토큰을 로그·브라우저 저장소에 남기지 않는다.
 */
import { useEffect, useState } from "react"
import { useLocation, useNavigate } from "react-router"

export const readHashToken = (hash: string): string | null => {
  const value = new URLSearchParams(hash.replace(/^#/, "")).get("token")
  return value?.trim() ? value.trim() : null
}

export const useLinkToken = (): string | null => {
  const location = useLocation()
  const navigate = useNavigate()
  const [token] = useState(() => readHashToken(location.hash))

  useEffect(() => {
    if (location.hash) {
      navigate({ pathname: location.pathname, search: location.search }, { replace: true })
    }
  }, [location.hash, location.pathname, location.search, navigate])

  return token
}
