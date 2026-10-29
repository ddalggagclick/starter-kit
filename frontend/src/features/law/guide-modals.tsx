/*
 * 담당: [A] | 책임: 사이드바 [상속 관계]·[상속세]로 여는 모달 내용(W-05·W-06 요약).
 * 근거: #227 최신 시안(https://claude.ai/artifact/NgrnTfYvGvuGj5PYWnJcfu) 모달 "상속 관계와 순위"·"상속세 안내".
 *   사용자 지시(2026-10-29): 기능·안전 때문에 시안과 다르게 두었던 부분도 시안대로 맞춘다 → 모달은 시안 문구·표를 그대로 쓴다.
 *   주소로 여는 /guide/relationship·/guide/tax 페이지는 전처럼 B1 검수 문구(guide-page.tsx)를 보인다.
 * 구현: 제목·부제 → 본문 → 아래쪽 [공식 사이트 링크] · [닫기]. [닫기]는 모달만 닫는다.
 * 제한사항: 개인별 상속인 판정·세액 계산을 하지 않는다.
 */
import { ExternalLink } from "lucide-react"
import type { ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { useOverlayStore } from "@/shared/state/overlay-store"

function ModalFrame({
  title,
  description,
  link,
  children,
}: {
  title: string
  description: string
  link: { title: string; url: string }
  children: ReactNode
}) {
  const close = useOverlayStore((s) => s.close)
  return (
    <div className="space-y-4">
      <div className="space-y-2 pr-8">
        <h2 className="text-lg font-semibold leading-none">{title}</h2>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      {children}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <a
          href={link.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex h-9 items-center justify-center gap-2 px-2 text-base font-medium text-primary underline-offset-4 hover:underline sm:mr-auto md:text-sm"
        >
          {link.title}
          <ExternalLink className="size-3.5" aria-hidden />
          <span className="sr-only">(새 창)</span>
        </a>
        <Button type="button" onClick={close}>
          닫기
        </Button>
      </div>
    </div>
  )
}

const RANKS = [
  ["1순위", "자녀 · 손자녀 등 직계비속"],
  ["2순위", "부모 · 조부모 등 직계존속"],
  ["3순위", "형제자매"],
  ["4순위", "4촌 이내 방계혈족"],
] as const

export function RelationshipModal() {
  return (
    <ModalFrame
      title="상속 관계와 순위"
      description="일반 설명입니다. 실제 상속인은 가족관계 서류와 공식 안내로 확인하세요."
      link={{ title: "국가법령정보센터", url: "https://www.law.go.kr" }}
    >
      <table className="w-full text-base sm:text-sm">
        <thead>
          <tr className="border-b">
            <th className="h-9 px-2 text-left font-medium text-muted-foreground">순위</th>
            <th className="h-9 px-2 text-left font-medium text-muted-foreground">상속인</th>
          </tr>
        </thead>
        <tbody>
          {RANKS.map(([rank, heirs]) => (
            <tr key={rank} className="border-b last:border-0">
              <td className="p-2">
                <span className="inline-flex items-center rounded-md bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">
                  {rank}
                </span>
              </td>
              <td className="p-2">{heirs}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="rounded-lg border px-4 py-3 text-base sm:text-sm">
        <p className="font-medium">배우자</p>
        <p className="text-muted-foreground">
          1순위 또는 2순위 상속인과 함께 상속인이 되고, 없으면 단독 상속인이 됩니다.
        </p>
      </div>
      <ul className="list-disc space-y-1.5 pl-5 text-base text-muted-foreground sm:text-sm">
        <li>
          같은 순위의 상속인이 여러 명이면 촌수가 가장 가까운 사람이 먼저 상속인이 되고, 촌수가 같은
          사람이 여러 명이면 함께 상속인이 됩니다. (민법 제1000조 제2항)
        </li>
        <li>태아는 상속 순위에서 이미 태어난 것으로 봅니다. (민법 제1000조 제3항)</li>
      </ul>
    </ModalFrame>
  )
}

export function TaxModal() {
  return (
    <ModalFrame
      title="상속세 안내"
      description="세액은 계산하지 않습니다. 신고 대상 여부는 국세청 안내를 확인하세요."
      link={{ title: "국세청 홈택스", url: "https://www.hometax.go.kr" }}
    >
      <div className="rounded-xl border p-4">
        <p className="text-xs font-medium text-muted-foreground">신고 기한</p>
        <p className="mt-1 text-xl font-semibold">달 말일부터 6개월</p>
        <p className="mt-1 text-base text-muted-foreground sm:text-sm">
          상속개시일이 속하는 달의 말일부터 6개월 이내 (상속세 및 증여세법 제67조 제1항)
          <br />
          피상속인이나 상속인이 외국에 주소를 둔 경우 9개월 (같은 법 제67조 제4항)
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 text-base sm:text-sm">
        <div className="rounded-xl border p-4">
          <p className="font-medium">홈택스</p>
          <p className="text-muted-foreground">전자 신고</p>
        </div>
        <div className="rounded-xl border p-4">
          <p className="font-medium">관할 세무서</p>
          <p className="text-muted-foreground">방문 신고</p>
        </div>
      </div>
    </ModalFrame>
  )
}
