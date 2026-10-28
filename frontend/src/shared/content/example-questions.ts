/*
 * 담당: [A] | 책임: 첫 화면 AI 대화창의 자주 묻는 예시 질문 문구.
 * 근거: #214(이슈 ⑤), 시안 https://claude.ai/artifact/T6VdodQVFJ3thyx4zpMyyN 2번(사용자 확인).
 * 구현: 대화창 위에 보일 5개(FEATURED)와 [+더보기] 모달(이슈 ⑥)에서 보일 주제별 전체 목록(GROUPS)을 둔다.
 *   누르면 질문창에 담기기만 한다(바로 보내지 않음, PRD 3-1-1).
 * 제한사항: **임시 문구다.** 실제 문구는 담당자가 이 파일만 고쳐 넣는다(사용자: "자주 쓰는 질문은 추가할 예정").
 *   각 질문은 AI 입력 한도(200자) 안이어야 하고 같은 질문을 두 번 넣지 않는다(시험이 확인).
 */

// 대화창 위에 칩으로 보이는 5개
export const FEATURED_EXAMPLE_QUESTIONS: readonly string[] = [
  "무엇부터 해야 하나요?",
  "상속포기 기한이 언제부터인가요?",
  "상속세 신고는 언제까지 하나요?",
  "사망신고는 어디서 하나요?",
  "한정승인이 무엇인가요?",
]

export type ExampleQuestionGroup = { title: string; questions: readonly string[] }

// [+더보기] 모달에서 주제별로 보이는 전체 목록. 위 5개도 포함한다.
export const EXAMPLE_QUESTION_GROUPS: readonly ExampleQuestionGroup[] = [
  {
    title: "절차 · 기한",
    questions: [
      "무엇부터 해야 하나요?",
      "사망신고는 어디서 하나요?",
      "안심상속 원스톱 서비스가 무엇인가요?",
      "상속포기 기한이 언제부터인가요?",
    ],
  },
  {
    title: "상속세",
    questions: ["상속세 신고는 언제까지 하나요?", "상속세는 누가 내나요?"],
  },
  {
    title: "채무 · 포기",
    questions: [
      "한정승인이 무엇인가요?",
      "빚이 더 많으면 어떻게 하나요?",
      "상속포기하면 다음 순위는 누구인가요?",
    ],
  },
  {
    title: "서류",
    questions: ["상속 절차에 필요한 서류는 무엇인가요?", "가족관계증명서는 어디서 떼나요?"],
  },
]
