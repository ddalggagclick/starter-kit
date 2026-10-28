/*
 * 담당: [A] | 책임: W-00 웹 첫 화면.
 * PRD: E2 / 태스크 2-1-1(W-00 진입), 5-6-1(로그인 없이 진입).
 * 구현: 시작 버튼으로 W-01, 이미 답한 상태면 W-02 이어 보기. 일반 안내(W-03·W-05·W-06) 입구.
 *   #210: 페이지 수를 줄이려고 카드 영역 자리에 AI 대화창(W-07 기능)을 넣었다. [AI에게 질문하기] 카드는 대화창과
 *   역할이 겹쳐 뺐고, 나머지 카드 3개는 대화창 아래에 둔다(사용자 결정). 헤더 메뉴가 찾아올 수 있게 id="ai"를 둔다.
 * 제한사항: 회원가입을 강제하지 않는다. 법률 판단을 대신하지 않는다는 안내를 둔다.
 */
import { ArrowRight, BookOpen, ListChecks, Scale } from "lucide-react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Notice } from "@/components/ui/notice"
import { HomeChatWindow } from "@/features/chat/home-chat-window"
import { COMMON_RISK_WARNING, LANDING_COPY, LEGAL_DISCLAIMER } from "@/shared/content/checklist"
import { useInheritanceStore } from "@/shared/state/inheritance-store"

const ENTRY_LINKS = [
  {
    to: "/procedures",
    icon: ListChecks,
    title: "전체 절차 보기",
    body: "공통 절차 8개를 둘러봅니다.",
  },
  {
    to: "/guide/relationship",
    icon: Scale,
    title: "상속 관계 알아보기",
    body: "상속 순위 일반 설명",
  },
  { to: "/guide/tax", icon: BookOpen, title: "상속세 기본 안내", body: "신고 기한·방법 일반 안내" },
] as const

export function LandingPage() {
  const hasAnswers = useInheritanceStore((state) => state.answers !== null)
  return (
    <div className="space-y-10">
      <section className="max-w-2xl space-y-4 pt-4">
        <p className="text-sm font-semibold text-muted-foreground">{LANDING_COPY.eyebrow}</p>
        <h1 className="text-3xl font-bold leading-tight tracking-tight sm:text-4xl">
          {LANDING_COPY.title}
        </h1>
        <p className="text-lg text-muted-foreground">{LANDING_COPY.description}</p>
        <div className="flex flex-wrap gap-3 pt-2">
          <Button asChild size="lg">
            <Link to="/start">
              {LANDING_COPY.startButton}
              <ArrowRight className="size-4" />
            </Link>
          </Button>
          {hasAnswers && (
            <Button asChild size="lg" variant="outline">
              <Link to="/checklist">내 체크리스트 이어 보기</Link>
            </Button>
          )}
        </div>
        <p className="text-sm text-muted-foreground">로그인하지 않아도 바로 시작할 수 있습니다.</p>
      </section>
      <Notice tone="warning">
        {COMMON_RISK_WARNING} {LEGAL_DISCLAIMER}.
      </Notice>
      <div id="ai" className="scroll-mt-4">
        <HomeChatWindow />
      </div>
      <section aria-label="안내 바로가기" className="grid gap-4 sm:grid-cols-3">
        {ENTRY_LINKS.map(({ to, icon: Icon, title, body }) => (
          <Link
            key={to}
            to={to}
            className="group rounded-xl focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Card className="h-full transition-colors group-hover:bg-muted">
              <CardHeader>
                <Icon className="size-5" aria-hidden />
                <CardTitle className="text-base">{title}</CardTitle>
                <CardDescription>{body}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </section>
    </div>
  )
}
