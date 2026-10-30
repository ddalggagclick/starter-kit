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
 *   (이전) UI 전면 개편 지시서 2장: 첫 화면 대화창 자리에 시작 카드 2개를 둔다(데스크톱 2열·모바일 세로, 카드 전체가 누르는 곳).
 *   - A [체크리스트 작성] → 질문 3개 모달(W-01) → 체크리스트. 답한 뒤면 [내 체크리스트 이어 보기]도 보인다.
 *   - B [AI 채팅] → /ai 전체 대화 화면. 체크리스트를 먼저 요구하지 않는다(선택 사항).
 *   - Hero는 사진·글을 한 덩어리로(글은 사진의 빈 하늘 쪽), 높이를 줄여 카드가 첫 화면에 보이게 한다.
 *     Hero의 시작 버튼은 카드 A와 같은 일을 해 중복이라 뺐다.
 *   추가 수정 지시서: 시작 카드 2개는 처음 들어올 때 여는 진입 선택 창(entry-gateway.tsx)으로 옮겼다. 첫 화면에는
 *   카드 영역을 다시 두지 않고, 두 기능은 오른쪽 아래 플로팅 내비게이션으로도 연다.
 *   사용자 지시(2026-10-30) "메인 랜딩 페이지를 짜봐": 히어로 아래에 ① 이용 방법 3단계 ② 믿고 쓸 수 있도록
 *   (공식 출처·법률 판단 안 함·동의한 경우만 저장)을 둔다. 공통 위험 경고 띠와 절차 8가지 미리보기는 사용자 지시로 뺐다. 시작 카드 영역과
 *   예전에 뺀 바로가기 카드 3개는 다시 만들지 않는다(시작은 진입 선택 창·플로팅 내비게이션). 새 기능·새 법률 문장 없음.
 *   간격은 황금비 리듬(구획 사이 block 32 / section 56, 칸 안 item 12 · group 20).
 * 제한사항: 회원가입을 강제하지 않는다. 법률 판단을 대신하지 않는다는 안내를 둔다.
 */
import { ExternalLink, Scale, ShieldCheck } from "lucide-react"
import { type ReactNode, useEffect } from "react"
import heroImage from "@/assets/home-hero.jpg"
import { LANDING_COPY } from "@/shared/content/checklist"
import { useOverlayStore } from "@/shared/state/overlay-store"
import { markEntryGatewayShown } from "./entry-gateway"

export function LandingPage() {
  const openOverlay = useOverlayStore((s) => s.open)
  // 이 탭에서 처음 첫 화면에 왔을 때만 진입 선택 창을 연다(다시 돌아와도 반복해서 열지 않는다).
  useEffect(() => {
    if (markEntryGatewayShown()) openOverlay("entry")
  }, [openOverlay])
  return (
    <div>
      <section aria-label="소개" className="relative -mx-4 overflow-hidden sm:mx-0 sm:rounded-2xl">
        <img
          src={heroImage}
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-[72%_center] sm:object-center"
        />
        <div className="hero-overlay absolute inset-0" aria-hidden />
        {/* 황금비(사용자 지시): 640px 이상은 히어로 높이 = 화면 높이의 61.8%, 글 칸 61.8% : 사진이 드러나는 칸 38.2%.
            글 칸 왼쪽 여백 0 → 제목·문구의 왼쪽 끝이 아래 본문(구획 제목·정보 오류 제보)과 같은 선(사용자 지시).
            모바일은 히어로가 화면 끝까지 붙으므로(-mx-4) 본문과 같은 16px(px-4)만 둔다.
            글자 크기(황금비 단계): 데스크톱 설명 20px × φ² ≈ 제목 52px, 640px 이상 42px, 모바일 36px(한 줄에 드는 최대).
            글 사이 간격 item 12px, 위아래 여백 block 32 / section 56. */}
        <div className="relative flex min-h-[24rem] flex-col gap-item px-4 pt-block pb-40 sm:min-h-[max(24rem,61.8svh)] sm:w-[61.8%] sm:justify-center sm:py-section sm:pr-block sm:pl-0">
          <p className="text-sm font-semibold text-muted-foreground sm:text-base">
            {LANDING_COPY.eyebrow}
          </p>
          <h1 className="text-[2.25rem] font-semibold leading-[1.2] tracking-tight text-primary sm:text-[2.625rem] lg:text-[3.25rem]">
            {LANDING_COPY.titleLines[0]}
            <br />
            {LANDING_COPY.titleLines[1]}
          </h1>
          <p className="text-base text-muted-foreground sm:text-lg">{LANDING_COPY.description}</p>
        </div>
      </section>

      {/* 사용자 지시(2026-10-30): 첫 화면에서만 공통 위험 경고 띠와 "상속 공통 절차 8가지" 구획을 뺐다.
          같은 경고는 체크리스트·절차 상세에 그대로 있고, 절차 목록은 사이드바 [전체 절차]·체크리스트에서 본다. */}
      <HowItWorks />
      <TrustNotes />
    </div>
  )
}

// 구획 공통 머리말: 제목(24px) + 한 줄 설명(16px). 구획 사이는 모바일 32 · 데스크톱 56px.
function LandingSection({
  id,
  title,
  description,
  children,
}: {
  id: string
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section aria-labelledby={id} className="mt-block space-y-group md:mt-section">
      <div className="space-y-2">
        <h2 id={id} className="text-xl font-semibold text-primary sm:text-2xl">
          {title}
        </h2>
        {description && <p className="text-base text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  )
}

const STEPS = [
  { title: "질문 3개에 답해요", body: "관계·사망일·원스톱 신청 여부만 물어요." },
  {
    title: "공통 절차를 확인해요",
    body: "8가지 절차를 순서대로, 기한과 주의할 점까지 볼 수 있어요.",
  },
  { title: "궁금한 건 AI에게 물어요", body: "답변마다 공식 출처를 함께 보여 드려요." },
] as const

// ① 이용 방법: 번호 + 제목 + 한 줄. 데스크톱 3열, 모바일 세로. 버튼 없음(시작은 진입 선택 창·플로팅 내비게이션).
function HowItWorks() {
  return (
    <LandingSection id="landing-how" title="이렇게 도와드려요">
      <ol className="grid gap-item md:grid-cols-3 md:gap-group">
        {STEPS.map((step, index) => (
          <li key={step.title} className="flex gap-item rounded-xl bg-emphasis p-group">
            <span
              aria-hidden
              className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-sm font-semibold text-primary-foreground"
            >
              {index + 1}
            </span>
            <div className="space-y-1">
              <p className="text-base font-semibold text-primary">{step.title}</p>
              <p className="text-sm text-muted-foreground">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </LandingSection>
  )
}

const TRUST = [
  {
    icon: ExternalLink,
    title: "공식 출처로 확인",
    body: "절차 안내와 AI 답변에 공식 링크를 함께 보여 드려요.",
  },
  {
    icon: Scale,
    title: "법률 판단은 대신하지 않아요",
    body: "실제 판단과 신고·신청은 공식 기관에서 확인하세요.",
  },
  {
    icon: ShieldCheck,
    title: "동의할 때만 저장",
    body: "체크리스트와 대화는 동의한 경우에만 이 기기에 저장해요.",
  },
] as const

// ② 믿고 쓸 수 있도록: 아이콘 + 제목 + 한 줄. 데스크톱 3열. 장식 없이 선 하나로 구획을 닫는다.
function TrustNotes() {
  return (
    <LandingSection id="landing-trust" title="믿고 쓸 수 있도록">
      <ul className="grid gap-group border-t pt-group md:grid-cols-3">
        {TRUST.map(({ icon: Icon, title, body }) => (
          <li key={title} className="flex gap-item">
            <Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
            <div className="space-y-1">
              <p className="text-base font-semibold text-primary">{title}</p>
              <p className="text-sm text-muted-foreground">{body}</p>
            </div>
          </li>
        ))}
      </ul>
    </LandingSection>
  )
}
