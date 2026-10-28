/*
 * 담당: [A] | 책임: 첫 화면 AI 대화창 위의 자주 묻는 예시 질문 칩.
 * 근거: #214(이슈 ⑤), 시안 2번(사용자 확인). 무엇을 물어야 할지 모르는 사용자가 예시를 눌러 바로 시작하게 한다.
 * 구현: 칩(둥근 버튼)을 누르면 onPick으로 질문을 넘긴다. 쓰는 쪽은 질문창에 담기만 하고 보내지 않는다(PRD 3-1-1).
 *   설명 문장 없이 칩만 둔다(사용자 요청: 문구 최소화). 화면낭독기에는 묶음 이름 "자주 묻는 질문"을 읽힌다.
 * 제한사항: 문구는 shared/content/example-questions.ts(임시). [+더보기] 모달은 이슈 ⑥에서 붙인다.
 */
import { FEATURED_EXAMPLE_QUESTIONS } from "@/shared/content/example-questions"

export function ExampleQuestions({ onPick }: { onPick: (question: string) => void }) {
  return (
    // fieldset은 묶음(group)으로 읽힌다. 기본 테두리·여백은 없앤다.
    <fieldset aria-label="자주 묻는 질문" className="m-0 flex min-w-0 flex-wrap gap-2 border-0 p-0">
      {FEATURED_EXAMPLE_QUESTIONS.map((question) => (
        <button
          key={question}
          type="button"
          onClick={() => onPick(question)}
          className="min-h-9 rounded-full border border-input bg-card px-3 py-1.5 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {question}
        </button>
      ))}
    </fieldset>
  )
}
