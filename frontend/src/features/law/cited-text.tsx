/*
 * 담당: [A] | 책임: 문장 끝 근거 조문 괄호를 다음 줄로 내려 보이는 작은 글 부품(상속 관계·상속세 안내 공용).
 * 근거: 사용자 지시(2026-10-30) "한 줄 글자 비율을 생각해 개행 위치 일괄 변경 — 예: 상속세 '6개월 이내' 다음 괄호는
 *   다음 줄". 문장과 출처를 한 줄에 섞으면 줄 길이가 들쭉날쭉해 읽기 어렵다.
 * 구현: "…(민법 제1000조 제2항)"처럼 끝에 '제N조'가 들어간 괄호가 있으면 본문과 나눠, 괄호는 새 줄에 보조 글씨로 보인다.
 *   조문 괄호가 없으면 그대로 보인다. 문구 자체는 바꾸지 않는다(출처 원문 유지).
 */
const CITATION = /\s*(\([^()]*제\d+조[^()]*\))\s*$/

export function splitCitation(text: string): [string, string | null] {
  const match = text.match(CITATION)
  if (!match || match.index === undefined) return [text, null]
  return [text.slice(0, match.index), match[1]]
}

export function CitedText({ text }: { text: string }) {
  const [body, citation] = splitCitation(text)
  return (
    <>
      {body}
      {/* 띄어쓰기를 남겨 화면낭독기·복사 때 본문과 괄호가 붙지 않게 한다(눈에는 줄바꿈으로 보인다). */}
      {citation && " "}
      {citation && (
        <span className="mt-0.5 block text-[0.875em] text-muted-foreground">{citation}</span>
      )}
    </>
  )
}
