/*
 * 담당: [A] | 책임: W-05 상속 관계 설명 · W-06 상속세 일반 안내.
 * PRD: E2 / 스토리 2-6 / 태스크 2-6-1 (W-08 버튼 2-6-3 연결).
 * 구현: B1 검수를 마친 정적 일반 설명(2026-10-26)과 공식 기관 링크를 보여준다.
 * 제한사항: 개인별 상속인 판정·세액 계산을 하지 않는다. 문구 근거와 검수 정보는 mocks/general-info.ts 상단에 있다.
 */
import { ExternalLink } from "lucide-react"
import { Notice } from "@/components/ui/notice"
import { FeedbackMockButton } from "@/features/reports/feedback-mock-dialog"
import { INHERITANCE_TAX_GUIDE, RELATIONSHIP_GUIDE } from "@/mocks/general-info"

type Guide = typeof RELATIONSHIP_GUIDE

function GuidePage({ screenId, guide }: { screenId: "W-05" | "W-06"; guide: Guide }) {
  return (
    <article className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-semibold text-muted-foreground">{screenId} · 일반 안내</p>
        <h1 className="text-2xl font-bold">{guide.title}</h1>
      </div>
      <Notice tone="warning">{guide.notice}</Notice>
      {guide.sections.map((section) => (
        <section key={section.heading} className="space-y-2 rounded-xl border bg-card p-5">
          <h2 className="font-semibold">{section.heading}</h2>
          <ul className="list-disc space-y-1 pl-5 leading-7">
            {section.body.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      ))}
      <section className="space-y-2">
        <h2 className="font-semibold">공식 출처</h2>
        <ul>
          {guide.officialLinks.map((link) => (
            <li key={link.url}>
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 underline underline-offset-4"
              >
                {link.title}
                <ExternalLink className="size-3.5" aria-hidden />
                <span className="sr-only">(새 창)</span>
              </a>
            </li>
          ))}
        </ul>
      </section>
      <div className="border-t pt-4">
        <FeedbackMockButton context={screenId} />
      </div>
    </article>
  )
}

export const RelationshipGuidePage = () => <GuidePage screenId="W-05" guide={RELATIONSHIP_GUIDE} />
export const TaxGuidePage = () => <GuidePage screenId="W-06" guide={INHERITANCE_TAX_GUIDE} />
