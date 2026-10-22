/*
 * 담당: [A] | 책임: 검증된 최종 답변을 자동 타이핑 효과로 보여준다.
 * PRD: E3 / 태스크 3-4-3. 루트 CLAUDE.md 4장(자동 타이핑, '다음 글자'·'전체 즉시 보기' 버튼 금지).
 * 구현: 코드 포인트 단위로 약 2초 안에 끝나도록 한 번에 여러 글자씩 늘린다. 사용자 조작 버튼은 없다.
 * 제한사항: 이미 검증되어 도착한 전체 본문만 받는다. 미검증 토큰을 흘려보내는 용도가 아니다.
 */
import { useEffect, useState } from "react"

const TICK_MS = 16
const TARGET_TICKS = 120

export const useTypewriter = (text: string) => {
  const [count, setCount] = useState(0)
  const characters = Array.from(text)
  const total = characters.length

  useEffect(() => {
    setCount(0)
    if (total === 0) return
    const step = Math.max(1, Math.ceil(total / TARGET_TICKS))
    const timer = setInterval(() => {
      setCount((current) => {
        const next = Math.min(total, current + step)
        if (next >= total) clearInterval(timer)
        return next
      })
    }, TICK_MS)
    return () => clearInterval(timer)
  }, [total])

  return { shown: characters.slice(0, count).join(""), done: count >= total }
}
