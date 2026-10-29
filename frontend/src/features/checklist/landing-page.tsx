/*
 * 담당: [A] | 책임: W-00 웹 첫 화면.
 * PRD: E2 / 태스크 2-1-1(W-00 진입), 5-6-1(로그인 없이 진입).
 * 구현: 시작 버튼으로 W-01(모달), 이미 답한 상태면 W-02 이어 보기. 일반 안내(W-03·W-05·W-06)는 사이드바 메뉴 모달로 연다(#227).
 *   #210: 페이지 수를 줄이려고 카드 영역 자리에 AI 대화창(W-07 기능)을 넣었다. [AI에게 질문하기] 카드는 대화창과
 *   역할이 겹쳐 뺐고, 나머지 카드 3개는 대화창 아래에 둔다(사용자 결정). 예전 주소 /ai가 찾아올 수 있게 id="ai"를 둔다.
 *   #227(새 시안 https://claude.ai/artifact/TuiF5t6g7WzBoez9bxFWov, 모양만 변경 — 사용자 지시 "기능은 절대 유지"):
 *   - 배너: 제목을 두 줄로 크게. [내 체크리스트 이어 보기]는 답한 뒤에만 보인다.
 *   - 카드 3개(공통 절차·상속 관계·상속세)는 사용자 요청으로 뺐다. 같은 안내는 사이드바 메뉴로 연다.
 *   - 공통 위험 경고: 첫 화면 위치 규정이 없어 시안대로 대화창 아래 작은 표시로 옮겼다. 문구는 그대로다.
 *   - 폭: 최신 시안처럼 본문 칸 전체(최대 1024px)를 쓴다.
 *   - Hero(최신 시안): 사진 위에 글을 얹고 배경색 그라데이션(index.css .hero-overlay)으로 사진이 바탕에 스며든다.
 *     글은 사진의 하늘·먼 풍경(왼쪽 위)에 두고 나무·길(오른쪽 아래)은 가리지 않는다. 사진은 꾸밈용이라 읽히지 않는다(alt="").
 *   - 새 시안(NgrnTfYvGvuGj5PYWnJcfu): [상속 절차 시작하기]는 페이지 이동 대신 질문 3개 모달을 연다(기존 /start 주소도 그대로).
 * 제한사항: 회원가입을 강제하지 않는다. 법률 판단을 대신하지 않는다는 안내를 둔다.
 */
import { ArrowRight, ListChecks } from "lucide-react"
import { Link } from "react-router"
import heroImage from "@/assets/home-hero.jpg"
import { Button } from "@/components/ui/button"
import { WarningPill } from "@/components/ui/notice"
import { HomeChatWindow } from "@/features/chat/home-chat-window"
import { COMMON_RISK_WARNING, LANDING_COPY, LEGAL_DISCLAIMER } from "@/shared/content/checklist"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import { useOverlayStore } from "@/shared/state/overlay-store"

export function LandingPage() {
  const hasAnswers = useInheritanceStore((state) => state.answers !== null)
  const openOverlay = useOverlayStore((s) => s.open)
  return (
    <div>
      <section aria-label="소개" className="relative -mx-4 overflow-hidden sm:mx-0">
        <img
          src={heroImage}
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-[72%_center] sm:object-center"
        />
        <div className="hero-overlay absolute inset-0" aria-hidden />
        <div className="relative flex min-h-[28rem] flex-col gap-3 px-5 pt-8 pb-44 sm:min-h-[24rem] sm:max-w-[36rem] sm:justify-center sm:px-10 sm:py-14 lg:min-h-[27rem] lg:px-12">
          <p className="text-sm font-semibold text-muted-foreground sm:text-base">
            {LANDING_COPY.eyebrow}
          </p>
          {/* 시안: 두 줄 큰 제목(모바일 30px, 640px 이상 45px) */}
          <h1 className="text-[1.875rem] font-semibold leading-tight tracking-tight sm:text-[2.8125rem]">
            {LANDING_COPY.titleLines[0]}
            <br />
            {LANDING_COPY.titleLines[1]}
          </h1>
          <p className="text-base text-muted-foreground sm:text-lg">{LANDING_COPY.description}</p>
          <div className="flex flex-wrap gap-2 pt-2">
            {/* 시안: 질문 3개를 지금 화면 위 모달로 연다. 답하면 체크리스트 화면으로 간다(기존과 같은 흐름). */}
            <Button
              type="button"
              aria-haspopup="dialog"
              className="h-11 px-6 font-semibold"
              onClick={() => openOverlay("start")}
            >
              {LANDING_COPY.startButton}
              <ArrowRight className="size-4" />
            </Button>
            {hasAnswers && (
              <Button asChild variant="outline" className="h-11">
                <Link to="/checklist">
                  <ListChecks className="size-4" aria-hidden />내 체크리스트 이어 보기
                </Link>
              </Button>
            )}
          </div>
        </div>
      </section>
      <div id="ai" className="mt-8 scroll-mt-16">
        <HomeChatWindow />
      </div>
      {/* 공통 위험 경고: 문구·읽힘(role="status")은 전과 같고, 모양만 작은 노란 표시로 바꿨다. */}
      <WarningPill className="mt-5">
        {COMMON_RISK_WARNING} {LEGAL_DISCLAIMER}.
      </WarningPill>
    </div>
  )
}
