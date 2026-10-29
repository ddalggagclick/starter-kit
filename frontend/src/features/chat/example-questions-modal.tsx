/*
 * 담당: [A] | 책임: [+더보기]로 여는 전체 예시 질문 모달.
 * 근거: #220(이슈 ⑥), 시안 2번(사용자 확인). 예시를 더 보고 싶을 때 화면을 어지럽히지 않고 모달에서 고르게 한다.
 * 구현: 공통 모달(#197 Modal)에 주제별 묶음과 칩을 보인다. 질문을 누르면 onPick으로 넘기고, 닫는 일은 쓰는 쪽이 한다.
 *   Esc·바깥 누르기·[닫기]로 닫히고 초점은 연 버튼으로 돌아간다(Modal이 처리).
 * 제한사항: 문구는 shared/content/example-questions.ts(임시)를 쓰는 쪽에서 받는다.
 */
import { Button } from "@/components/ui/button"
import { Modal } from "@/components/ui/modal"
import { cn } from "@/lib/utils"
import type { ExampleQuestionGroup } from "@/shared/content/example-questions"
import { CHIP_CLASS } from "./example-questions"

export function ExampleQuestionsModal({
  groups,
  onPick,
  onClose,
}: {
  groups: readonly ExampleQuestionGroup[]
  onPick: (question: string) => void
  onClose: () => void
}) {
  return (
    <Modal onClose={onClose}>
      {/* #227 시안: 부제와 칩 모양을 첫 화면 칩과 같게. 긴 질문은 모달 안에서 줄을 바꾼다. */}
      <Modal.Header title="자주 묻는 질문" subtitle="누르면 질문창에 담깁니다." />
      <Modal.Body className="space-y-4">
        {groups.map((group) => (
          <fieldset key={group.title} className="m-0 min-w-0 space-y-2 border-0 p-0">
            <legend className="mb-2 text-sm font-medium text-muted-foreground">
              {group.title}
            </legend>
            <div className="flex flex-wrap gap-2">
              {group.questions.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => onPick(question)}
                  className={cn(CHIP_CLASS, "h-auto min-h-9 whitespace-normal py-1.5 text-left")}
                >
                  {question}
                </button>
              ))}
            </div>
          </fieldset>
        ))}
      </Modal.Body>
      <Modal.Actions>
        <Button type="button" variant="outline" onClick={onClose}>
          닫기
        </Button>
      </Modal.Actions>
    </Modal>
  )
}
