/*
 * 담당: [A] | 책임: 처음 들어올 때 첫 화면 위에 여는 진입 선택 창(Entry Gateway).
 * 근거: UI·UX 추가 수정 지시서(진입 모달) 1·2장. 첫 화면 안에 있던 시작 카드 2개를 이 창으로 옮겼다.
 * 구현: 두 카드는 크기·글씨·색·테두리·아이콘·hover/focus가 모두 같다(동등한 시작 경로).
 *   - [체크리스트로 시작하기]: 답한 적이 있으면 체크리스트로, 없으면 질문 3개(W-01) 창으로 바꿔 연다.
 *   - [AI에게 질문하기]: /ai 전체 대화 화면으로 간다(체크리스트를 요구하지 않음).
 *   추가 개선 지시서 1장(재설계): 전 모양은 창 제목(20px)과 카드 제목(20px)이 같은 크기라 위계가 없고, 카드 안
 *   가로 배치(아이콘·글·화살표) 때문에 제목이 "체크리스트로 시 / 작하기"처럼 끊겼으며, 테두리·화살표가 시선을 나눴다.
 *   → ① 머리(제목 26/32px · 설명 16px, 약 1.6배)와 ② 선택 영역을 큰 간격(26/42px)으로 나누고, 카드는 세로 배치
 *   (아이콘 → 제목 20px → 설명 14px)로 바꿔 줄바꿈 없이 읽히게 했다. 카드는 테두리·화살표 없이 밝은 블루 바탕 하나,
 *   데스크톱 카드 비율은 약 1.618:1(min-h). 간격 단계는 16 → 26 → 42px(황금비 근사)로 맞췄다.
 *   - 닫기(Esc·바깥·[닫기])는 건너뛰기와 같다. 한 번 열면 이 탭에서는 다시 열지 않는다(저장하지 않는 메모리 표시).
 */
import { ListChecks, MessageCircle } from "lucide-react"
import type { ReactNode } from "react"
import { Link, useNavigate } from "react-router"
import { useHandoffFlight } from "@/features/kakao/use-handoff"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { useOverlayStore } from "@/shared/state/overlay-store"

// 새로고침 전까지 한 번만 연다. 개인정보가 아닌 화면 표시 여부라 저장하지 않는다(재방문 시 다시 보인다).
let entryGatewayShown = false
export const markEntryGatewayShown = () => {
  const first = !entryGatewayShown
  entryGatewayShown = true
  return first
}
// 시험용: 다음 시험이 처음 들어온 상태에서 시작하도록 되돌린다.
export const resetEntryGatewayForTest = () => {
  entryGatewayShown = false
}

// 두 카드 공통(동등한 위계): 같은 바탕·여백·최소 높이, hover/focus/active도 같다.
export const START_CARD_CLASS =
  "flex h-full w-full flex-col items-start rounded-2xl bg-start-card p-6 text-left outline-none ring-1 ring-transparent transition-shadow hover:ring-primary/30 focus-visible:ring-[3px] focus-visible:ring-ring/50 active:ring-primary/50 md:min-h-[10.5rem]"

function StartCardBody({
  icon,
  title,
  description,
}: {
  icon: ReactNode
  title: string
  description: ReactNode
}) {
  return (
    <>
      <span className="grid size-11 place-items-center rounded-xl bg-primary text-primary-foreground">
        {icon}
      </span>
      <span className="mt-4 block text-lg font-semibold leading-snug text-primary">{title}</span>
      <span className="mt-1.5 block text-sm leading-relaxed text-muted-foreground [word-break:keep-all]">
        {description}
      </span>
    </>
  )
}

export function EntryGateway() {
  const hasAnswers = useInheritanceStore((state) => state.answers !== null)
  const handoffInFlight = useHandoffFlight((s) => s.inFlight)
  const openOverlay = useOverlayStore((s) => s.open)
  const navigate = useNavigate()
  return (
    <div>
      {/* 오른쪽 위 닫기(X)와 제목이 겹치지 않게 머리말만 오른쪽을 비운다(본문 좌우 여백은 같게). */}
      <header className="space-y-2.5 pr-10">
        <h2 className="text-[1.625rem] font-semibold leading-tight tracking-tight text-primary sm:text-[2rem]">
          어떻게 시작할까요?
        </h2>
        {/* 사용자 지정 줄바꿈: "정리하거나," 뒤. 낱말 중간에서 끊기지 않게 keep-all. */}
        <p className="text-base leading-relaxed text-muted-foreground [word-break:keep-all]">
          절차를 차근차근 정리하거나,
          <br />
          궁금한 점을 바로 물어볼 수 있어요.
        </p>
      </header>
      <div className="mt-[1.625rem] grid gap-4 sm:mt-[2.625rem] md:grid-cols-2">
        <button
          type="button"
          className={START_CARD_CLASS}
          // 답이 있거나 카카오 인계 답을 받는 중이면 체크리스트로(받는 중이면 스켈레톤으로 기다림), 아니면 질문 3개.
          onClick={() =>
            hasAnswers || handoffInFlight ? navigate("/checklist") : openOverlay("start")
          }
        >
          <StartCardBody
            icon={<ListChecks className="size-5" aria-hidden />}
            title="체크리스트로 시작하기"
            description={
              <>
                질문 3개에 답하면 해야 할 절차를
                <br />
                순서대로 보여 드려요.
              </>
            }
          />
        </button>
        <Link to="/ai" className={START_CARD_CLASS}>
          <StartCardBody
            icon={<MessageCircle className="size-5" aria-hidden />}
            title="AI에게 질문하기"
            description={
              <>
                체크리스트 없이 궁금한 점을
                <br />
                바로 물어보세요.
              </>
            }
          />
        </Link>
      </div>
    </div>
  )
}
