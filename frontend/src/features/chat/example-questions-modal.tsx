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
    // #246: 질문이 덜 줄바꿈되게 넓음 폭(40.5rem, 황금비 3단계 중 가장 넓음)을 쓴다. 모바일은 화면 폭(w-full)을 넘지 않는다.
    <Modal onClose={onClose} className="max-w-[40.5rem]">
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
                  // #246 팀 피드백: 칩 줄의 shrink-0 때문에 모바일에서 긴 질문이 오른쪽으로 잘렸다.
                  //   모달 안쪽 폭(max-w-full)까지 줄어들게(shrink) 하고, 긴 낱말도 줄을 바꾸게(break-words) 한다.
                  className={cn(
                    CHIP_CLASS,
                    "h-auto min-h-9 max-w-full shrink whitespace-normal break-words py-1.5 text-left",
                  )}
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
