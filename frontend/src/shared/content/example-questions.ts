/*
 * 담당: [A] | 책임: 첫 화면 AI 대화창의 자주 묻는 예시 질문 문구.
 * 근거: #214(이슈 ⑤), #227 사용자 제공 문구(2026-10-29), #246 팀 피드백 문구(2026-11-02) — 짧은 질문으로 바꿨다.
 * 구현: [더보기] 모달에 보일 주제별 전체 목록(GROUPS, 주제 4개 × 2개 = 8개)과, 대화창 위 칩 줄에 보일 질문(FEATURED: 주제마다
 *   첫 질문 1개씩, 4개)을 둔다. FEATURED는 GROUPS에서 뽑아 대화창 위 질문이 늘 모달 목록에도 있다.
 *   누르면 질문창에 담기기만 한다(바로 보내지 않음, PRD 3-1-1).
 * 제한사항: 각 질문은 AI 입력 한도(200자) 안이어야 하고 같은 질문을 두 번 넣지 않는다(시험이 확인).
 */

export type ExampleQuestionGroup = { title: string; questions: readonly string[] }

// [더보기] 모달에서 주제별로 보이는 전체 목록(#246 팀 제공 문구 그대로)
export const EXAMPLE_QUESTION_GROUPS: readonly ExampleQuestionGroup[] = [
  {
    title: "절차 · 기한",
    questions: ["안심상속 신청처와 조회 대상은?", "포기·한정승인 기한과 신고 법원은?"],
  },
  {
    title: "상속세",
    questions: ["상속세 신고기한은 사망월 기준 언제까지?", "홈택스 상속세 신고 메뉴는?"],
  },
  {
    title: "채무 · 포기",
    questions: [
      "고인 금융채무는 어디서 조회하나요?",
      "포기·한정승인 시 빚 처리는 어떻게 다른가요?",
    ],
  },
  {
    title: "서류",
    questions: ["한정승인 신고서류는 무엇인가요?", "가족관계증명서 발급처는?"],
  },
]

// 대화창 위 칩 줄: 주제마다 첫 질문 1개씩(4개). 나머지는 [더보기] 모달에서 고른다.
export const FEATURED_EXAMPLE_QUESTIONS: readonly string[] = EXAMPLE_QUESTION_GROUPS.map(
  (group) => group.questions[0],
)
