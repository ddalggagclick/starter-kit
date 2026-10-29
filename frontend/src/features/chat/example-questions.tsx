/*
 * 담당: [A] | 책임: 첫 화면 AI 대화창 위의 자주 묻는 예시 질문 칩.
 * 근거: #214(이슈 ⑤), 시안 2번(사용자 확인). 무엇을 물어야 할지 모르는 사용자가 예시를 눌러 바로 시작하게 한다.
 * 구현: 칩(둥근 버튼)을 누르면 onPick으로 질문을 넘긴다. 쓰는 쪽은 질문창에 담기만 하고 보내지 않는다(PRD 3-1-1).
 *   설명 문장 없이 칩만 둔다(사용자 요청: 문구 최소화). 화면낭독기에는 묶음 이름 "자주 묻는 질문"을 읽힌다.
 *   #220: 전체 목록이 5개보다 많으면 [더보기]를 두고, 누르면 전체 예시 모달을 연다.
 *   모달에서 고르면 모달을 먼저 닫은 뒤(flushSync) 질문을 넘긴다. 그래야 모달이 연 버튼으로 돌려주는 초점보다
 *   쓰는 쪽이 옮기는 질문창 초점이 나중에 적용된다.
 *   #227 최신 시안(NgrnTfYvGvuGj5PYWnJcfu): 예시는 한 줄이다. 칩 줄은 옆으로 밀어(스크롤) 나머지를 보고, 넘칠 때만
 *   오른쪽 끝을 흐리게 한다(끝까지 밀면 흐림이 사라진다). 마우스 휠(세로)로도 옆으로 민다. [더보기]는 줄 밖 오른쪽에 둔다.
 *   모든 칩이 그대로 있어 Tab·화면낭독기로도 다 닿는다.
 * 제한사항: 문구는 shared/content/example-questions.ts(임시).
 */
import { Plus } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { flushSync } from "react-dom"
import { cn } from "@/lib/utils"
import {
  EXAMPLE_QUESTION_GROUPS,
  FEATURED_EXAMPLE_QUESTIONS,
} from "@/shared/content/example-questions"
import { ExampleQuestionsModal } from "./example-questions-modal"

// 칩 모양(시안): 높이 36px, 글자 15px·굵기 500, 옅은 그림자, 올리면 살짝 떠오른다. 모달 안 칩도 같은 모양을 쓴다.
//   앱 토큰은 font-medium을 400으로 정해 두어, 시안과 같은 굵기를 쓰려고 500을 직접 적는다.
export const CHIP_CLASS =
  "inline-flex h-9 shrink-0 max-md:min-h-11 items-center gap-1.5 whitespace-nowrap rounded-full border bg-card px-3.5 text-[15px] font-[500] shadow-[0_1px_2px_rgb(18_54_87/0.08),0_3px_8px_-2px_rgb(18_54_87/0.14)] outline-none transition-[background-color,box-shadow,transform] hover:-translate-y-px hover:bg-accent hover:text-accent-foreground hover:shadow-[0_2px_4px_rgb(18_54_87/0.1),0_6px_14px_-4px_rgb(18_54_87/0.18)] focus-visible:ring-[3px] focus-visible:ring-ring/50"

// 모달에서만 볼 수 있는 예시가 있으면 [더보기]를 보인다.
const HAS_MORE =
  new Set(EXAMPLE_QUESTION_GROUPS.flatMap((group) => group.questions)).size >
  FEATURED_EXAMPLE_QUESTIONS.length

// 칩 줄이 넘치고 아직 끝까지 밀지 않았으면 오른쪽 끝을 흐리게(is-overflow) 한다. 휠(세로)도 옆으로 밀게 한다.
function useChipRow() {
  const rowRef = useRef<HTMLDivElement>(null)
  const [overflow, setOverflow] = useState(false)
  useEffect(() => {
    const row = rowRef.current
    if (!row) return
    const updateFade = () =>
      setOverflow(
        row.scrollWidth > row.clientWidth + 1 &&
          row.scrollLeft + row.clientWidth < row.scrollWidth - 2,
      )
    const onWheel = (event: WheelEvent) => {
      if (row.scrollWidth > row.clientWidth && Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
        row.scrollLeft += event.deltaY
        event.preventDefault()
      }
    }
    updateFade()
    row.addEventListener("scroll", updateFade)
    row.addEventListener("wheel", onWheel, { passive: false })
    window.addEventListener("resize", updateFade)
    return () => {
      row.removeEventListener("scroll", updateFade)
      row.removeEventListener("wheel", onWheel)
      window.removeEventListener("resize", updateFade)
    }
  }, [])
  return { rowRef, overflow }
}

export function ExampleQuestions({ onPick }: { onPick: (question: string) => void }) {
  const [moreOpen, setMoreOpen] = useState(false)
  const { rowRef, overflow } = useChipRow()

  const pickFromModal = (question: string) => {
    flushSync(() => setMoreOpen(false))
    onPick(question)
  }

  return (
    <>
      {/* 묶음(group)으로 읽힌다. fieldset은 브라우저가 flex 높이를 다르게 계산해 대화창과의 간격(12px)이 사라져
          div role="group"으로 바꿨다(#227, 시안과 실측 비교). */}
      {/* biome-ignore lint/a11y/useSemanticElements: fieldset은 flex 높이 계산이 달라 시안 간격이 깨진다. role="group"으로 같은 묶음 의미를 준다. */}
      <div role="group" aria-label="자주 묻는 질문" className="flex min-w-0 items-center gap-2">
        {/* 한 줄 칩 줄: 위아래 여백(py-2)은 그림자·초점 테두리가 잘리지 않게, 바깥 여백(-my-2)으로 자리를 되돌린다. */}
        <div
          ref={rowRef}
          data-testid="example-chip-row"
          className={cn(
            "chip-row -my-2 flex min-w-0 flex-1 flex-nowrap gap-2 overflow-x-auto px-0.5 py-2",
            overflow && "is-overflow",
          )}
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
        </div>
        {HAS_MORE && (
          <button
            type="button"
            aria-haspopup="dialog"
            onClick={() => setMoreOpen(true)}
            className={cn(CHIP_CLASS, "border-dashed text-primary")}
          >
            <Plus className="size-3.5" aria-hidden />
            더보기
          </button>
        )}
      </div>
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
