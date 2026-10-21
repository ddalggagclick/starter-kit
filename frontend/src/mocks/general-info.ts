/*
 * 담당: [A] | 책임: W-05 상속 관계 · W-06 상속세 · W-08 오류 제보 Mock 문구.
 * 근거: 화면정의서 v1.4 06장(유지 화면), PRD 2-6-1·2-6-3·2-6-4.
 * 제한사항: 일반 설명이며 개인별 상속인 판정·세액 계산을 하지 않는다. B1 검수 전 예시 문구다.
 *   W-08은 외부 Google Forms 연결 예정이나 주소가 정해지지 않아 Mock 모달만 둔다(실제 전송 없음).
 */
import type { OfficialLink } from "./wire-types"

export type InfoSection = { heading: string; body: string[] }

export const RELATIONSHIP_GUIDE: {
  title: string
  notice: string
  sections: InfoSection[]
  officialLinks: OfficialLink[]
} = {
  title: "내 상속 관계 알아보기",
  notice: "일반 설명입니다. 실제 상속인은 가족관계 서류와 공식 안내로 확인하세요. (검수 전 Mock)",
  sections: [
    {
      heading: "상속 순위 (일반 설명)",
      body: [
        "1순위: 자녀 · 손자녀 등 직계비속",
        "2순위: 부모 · 조부모 등 직계존속",
        "3순위: 형제자매",
        "4순위: 4촌 이내 방계혈족",
      ],
    },
    {
      heading: "배우자",
      body: ["배우자는 1순위 또는 2순위 상속인과 함께 상속인이 되고, 없으면 단독 상속인이 됩니다."],
    },
  ],
  officialLinks: [{ title: "국가법령정보센터", url: "https://www.law.go.kr" }],
}

export const INHERITANCE_TAX_GUIDE: {
  title: string
  notice: string
  sections: InfoSection[]
  officialLinks: OfficialLink[]
} = {
  title: "상속세 기본 안내",
  notice:
    "이 서비스는 세액을 계산하지 않습니다. 신고 대상 여부는 국세청 안내를 확인하세요. (검수 전 Mock)",
  sections: [
    {
      heading: "신고 기한 (일반 안내)",
      body: ["상속개시일이 속한 달의 말일부터 6개월 이내로 안내됩니다. (예시 문구 · 검증 필요)"],
    },
    {
      heading: "신고 방법",
      body: ["홈택스 전자 신고", "관할 세무서 방문 신고"],
    },
  ],
  officialLinks: [{ title: "국세청 홈택스", url: "https://www.hometax.go.kr" }],
}

// W-08 Mock 모달. 입력을 저장·전송하지 않는다(PRD 2-6-4).
export const FEEDBACK_MOCK_COPY = {
  button: "정보 오류 제보",
  title: "정보 오류 제보 (준비 중)",
  body: "오류 제보 기능은 MVP 이후 제공됩니다. 지금은 입력해도 전송되거나 저장되지 않습니다.",
  close: "닫기",
} as const
