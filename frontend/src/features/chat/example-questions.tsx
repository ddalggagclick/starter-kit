/*
 * 담당: [A] | 책임: 첫 화면 AI 대화창 위의 자주 묻는 예시 질문 칩.
 * 근거: #214(이슈 ⑤), 시안 2번(사용자 확인). 무엇을 물어야 할지 모르는 사용자가 예시를 눌러 바로 시작하게 한다.
 * 구현: 칩(둥근 버튼)을 누르면 onPick으로 질문을 넘긴다. 쓰는 쪽은 질문창에 담기만 하고 보내지 않는다(PRD 3-1-1).
 *   설명 문장 없이 칩만 둔다(사용자 요청: 문구 최소화). 화면낭독기에는 묶음 이름 "자주 묻는 질문"을 읽힌다.
 *   #220: 전체 목록이 5개보다 많으면 끝에 [+ 더보기]를 두고, 누르면 전체 예시 모달을 연다.
 *   모달에서 고르면 모달을 먼저 닫은 뒤(flushSync) 질문을 넘긴다. 그래야 모달이 연 버튼으로 돌려주는 초점보다
 *   쓰는 쪽이 옮기는 질문창 초점이 나중에 적용된다.
 * 제한사항: 문구는 shared/content/example-questions.ts(임시).
 */
import { useState } from "react"
import { flushSync } from "react-dom"
import {
  EXAMPLE_QUESTION_GROUPS,
  FEATURED_EXAMPLE_QUESTIONS,
} from "@/shared/content/example-questions"
import { ExampleQuestionsModal } from "./example-questions-modal"

// 칩 모양. [+ 더보기]도 같은 크기로 둔다.
const CHIP_CLASS =
  "min-h-9 rounded-full border border-input bg-card px-3 py-1.5 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

// 모달에서만 볼 수 있는 예시가 있을 때만 [+ 더보기]를 보인다.
const HAS_MORE =
  new Set(EXAMPLE_QUESTION_GROUPS.flatMap((group) => group.questions)).size >
  FEATURED_EXAMPLE_QUESTIONS.length

export function ExampleQuestions({ onPick }: { onPick: (question: string) => void }) {
  const [moreOpen, setMoreOpen] = useState(false)

  const pickFromModal = (question: string) => {
    flushSync(() => setMoreOpen(false))
    onPick(question)
  }

  return (
    <>
      {/* fieldset은 묶음(group)으로 읽힌다. 기본 테두리·여백은 없앤다. */}
      <fieldset
        aria-label="자주 묻는 질문"
        className="m-0 flex min-w-0 flex-wrap gap-2 border-0 p-0"
      >
        {FEATURED_EXAMPLE_QUESTIONS.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onPick(question)}
            className={CHIP_CLASS}
          >
            {question}
          </button>
        ))}
        {HAS_MORE && (
          <button
            type="button"
            aria-haspopup="dialog"
            onClick={() => setMoreOpen(true)}
            className={`${CHIP_CLASS} border-dashed font-semibold text-primary`}
          >
            + 더보기
          </button>
        )}
      </fieldset>
      {/* 모달은 묶음 밖에 둔다(화면낭독기가 예시 묶음 안의 대화상자로 읽지 않게). */}
      {moreOpen && (
        <ExampleQuestionsModal
          groups={EXAMPLE_QUESTION_GROUPS}
          onPick={pickFromModal}
          onClose={() => setMoreOpen(false)}
        />
      )}
    </>
  )
}
