/*
 * 담당: [A] | 책임: A07 절차 목록·상세 Mock 데이터 (W-02·W-03·W-04·K-04 표시용).
 * 근거: openapi.yaml A07, 화면정의서 v1.4 06·07장(W-04 B 접기형), 부록3.
 * 제한사항: 절차 이름·문구·기한은 검수 전 예시다(B3 검수, S01 URL 확정 전).
 *   p01~p08과 절차 이름의 대응은 D6 보류이므로 Mock 배정이다. 실제 안내로 배포하지 않는다.
 *   공식 링크는 기관 대표 주소만 쓰고 세부 페이지 URL을 만들지 않는다.
 */
import type { ProcedureId } from "@/shared/contracts/domain"
import type { ProcedureDetail, ProcedureSummary } from "./wire-types"

export const PROCEDURE_IDS: readonly ProcedureId[] = [
  "p01",
  "p02",
  "p03",
  "p04",
  "p05",
  "p06",
  "p07",
  "p08",
]

// 표시 순서는 공통 안내 순서일 뿐 법적 우선순위가 아니다(PRD 2-2-1).
export const MOCK_PROCEDURE_SUMMARIES: ProcedureSummary[] = [
  {
    procedureId: "p01",
    name: "사망신고 · 안심상속 원스톱 서비스",
    summary: "사망신고와 함께 고인의 재산 조회를 한 번에 신청하는 방법을 확인합니다.",
  },
  {
    procedureId: "p02",
    name: "상속인 확인",
    summary: "가족관계 서류로 상속인이 누구인지 확인합니다.",
  },
  {
    procedureId: "p03",
    name: "재산 · 채무 확인",
    summary: "예금·부동산·채무 등 고인의 재산과 빚을 공식 조회로 확인합니다.",
  },
  {
    procedureId: "p04",
    name: "상속포기 · 한정승인",
    summary: "채무가 걱정될 때 법원에 신고하는 절차와 기한을 확인합니다.",
  },
  {
    procedureId: "p05",
    name: "상속재산 분할 협의",
    summary: "상속인끼리 재산을 어떻게 나눌지 협의하는 방법을 확인합니다.",
  },
  {
    procedureId: "p06",
    name: "금융재산 상속 처리",
    summary: "예금 인출·명의변경 등 금융회사 절차를 확인합니다.",
  },
  {
    procedureId: "p07",
    name: "부동산 상속등기",
    summary: "상속받은 부동산의 소유권 이전 등기 절차를 확인합니다.",
  },
  {
    procedureId: "p08",
    name: "상속세 신고",
    summary: "상속세 신고 대상 여부와 신고 방법을 확인합니다.",
  },
]

// W-02 절차 카드 기한 꼬리표. 화면정의서 05장: "기한 문구는 예시, 검증 필요".
export const MOCK_DEADLINE_TAGS: Partial<Record<ProcedureId, string>> = {
  p01: "1개월 기한",
  p04: "3개월 기한 · 가장 시급",
  p08: "6개월 기한",
}

const LINK_GOV24 = { title: "정부24", url: "https://www.gov.kr" }
const LINK_EFAMILY = {
  title: "대법원 전자가족관계등록시스템",
  url: "https://efamily.scourt.go.kr",
}
const LINK_ECFS = { title: "대법원 전자소송", url: "https://ecfs.scourt.go.kr" }
const LINK_KLAC = { title: "대한법률구조공단", url: "https://www.klac.or.kr" }
const LINK_IROS = { title: "대법원 인터넷등기소", url: "https://www.iros.go.kr" }
const LINK_HOMETAX = { title: "국세청 홈택스", url: "https://www.hometax.go.kr" }
const LINK_LAW = { title: "국가법령정보센터", url: "https://www.law.go.kr" }

export const MOCK_PROCEDURE_DETAILS: Record<ProcedureId, ProcedureDetail> = {
  p01: {
    procedureId: "p01",
    action: "주민센터나 정부24에서 사망신고와 안심상속 원스톱 서비스 신청 방법을 확인하세요.",
    deadline: "사망신고는 사망 사실을 안 날부터 1개월 이내로 안내됩니다. (예시 문구 · 검증 필요)",
    risk: "신고 기한과 과태료 여부는 개별 상황에 따라 다를 수 있습니다.",
    agency: "시·구·읍·면·동 주민센터 · 정부24",
    documents: [
      "사망진단서 또는 시체검안서",
      "신고인 신분증",
      "안심상속 원스톱 서비스 신청서",
      "대리 신청 시 위임 관련 서류",
    ],
    methods: ["주민센터 방문 신청", "정부24 온라인 신청(대상자에 한함)"],
    exceptions: ["사망 장소·신고인 자격에 따라 제출 서류가 달라질 수 있습니다."],
    contacts: ["가까운 주민센터", "정부민원안내콜센터 110"],
    officialLinks: [LINK_GOV24],
    relatedProcedureIds: ["p02", "p03"],
  },
  p02: {
    procedureId: "p02",
    action: "가족관계증명서 등으로 상속인 범위를 확인하세요.",
    deadline: "별도 기한은 없지만 다른 절차의 전제가 됩니다. (예시 문구 · 검증 필요)",
    risk: "상속인 범위는 가족 구성과 상속포기 여부에 따라 달라질 수 있습니다.",
    agency: "주민센터 · 대법원 전자가족관계등록시스템",
    documents: ["고인의 기본증명서", "고인의 가족관계증명서", "고인의 제적등본(필요 시)"],
    methods: ["주민센터 방문 발급", "전자가족관계등록시스템 온라인 발급"],
    exceptions: ["선순위 상속인이 상속을 포기하면 다음 순위로 넘어갈 수 있습니다."],
    contacts: ["가까운 주민센터"],
    officialLinks: [LINK_EFAMILY],
    relatedProcedureIds: ["p04", "p05"],
  },
  p03: {
    procedureId: "p03",
    action: "안심상속 원스톱 서비스 조회 결과로 재산과 채무를 확인하세요.",
    deadline: "상속포기·한정승인 기한 안에 확인하는 것이 좋습니다. (예시 문구 · 검증 필요)",
    risk: "조회 결과에 나오지 않는 채무·보증이 있을 수 있습니다.",
    agency: "정부24 · 각 조회 기관",
    documents: ["안심상속 원스톱 서비스 접수증", "상속인 신분증"],
    methods: ["정부24에서 조회 결과 확인", "각 기관 누리집에서 결과 확인"],
    exceptions: ["조회 대상 기관이 아닌 개인 간 채무는 따로 확인해야 합니다."],
    contacts: ["정부민원안내콜센터 110"],
    officialLinks: [LINK_GOV24],
    relatedProcedureIds: ["p04", "p08"],
  },
  p04: {
    procedureId: "p04",
    action: "법원 신고 절차와 필요 서류를 확인하세요.",
    deadline: "상속 개시가 있음을 안 날부터 3개월 이내로 안내됩니다. (예시 문구 · 검증 필요)",
    risk: "신청 자격은 상황과 시점에 따라 다를 수 있습니다. 재산을 처분·사용하면 영향이 있을 수 있습니다.",
    agency: "관할 가정법원 (대상 · 조건은 법원 안내 확인)",
    documents: [
      "상속포기 또는 한정승인 심판청구서",
      "고인의 기본증명서·가족관계증명서",
      "청구인의 인감증명서",
      "재산 목록(한정승인 시)",
    ],
    methods: ["관할 가정법원 방문 접수", "대법원 전자소송 온라인 접수"],
    exceptions: ["기한이 지난 뒤 채무를 알게 된 경우 별도 제도가 있을 수 있습니다."],
    contacts: ["관할 가정법원 민원실", "대한법률구조공단 132"],
    officialLinks: [LINK_ECFS, LINK_KLAC],
    relatedProcedureIds: ["p03", "p02"],
  },
  p05: {
    procedureId: "p05",
    action: "상속인 전원이 참여하는 분할 협의 방법을 확인하세요.",
    deadline: "법정 기한은 없지만 등기·세금 절차와 연결됩니다. (예시 문구 · 검증 필요)",
    risk: "상속인 일부가 빠진 협의는 효력 문제가 생길 수 있습니다.",
    agency: "상속인 간 협의 · 다툼이 있으면 가정법원",
    documents: ["상속재산분할협의서", "상속인 전원의 인감증명서", "가족관계 서류"],
    methods: ["상속인 전원 서명·날인", "협의가 안 되면 법원 조정·심판"],
    exceptions: ["미성년 상속인이 있으면 특별대리인이 필요할 수 있습니다."],
    contacts: ["대한법률구조공단 132"],
    officialLinks: [LINK_KLAC],
    relatedProcedureIds: ["p02", "p07"],
  },
  p06: {
    procedureId: "p06",
    action: "금융회사별 상속 예금 인출·명의변경 절차를 확인하세요.",
    deadline: "기관마다 다릅니다. (예시 문구 · 검증 필요)",
    risk: "상속포기·한정승인을 고려 중이면 인출 전에 영향을 먼저 확인하세요.",
    agency: "각 금융회사",
    documents: ["가족관계 서류", "상속인 신분증", "상속재산분할협의서(필요 시)"],
    methods: ["금융회사 영업점 방문"],
    exceptions: ["소액 예금은 간소화 절차가 있을 수 있습니다."],
    contacts: ["각 금융회사 고객센터"],
    officialLinks: [LINK_GOV24],
    relatedProcedureIds: ["p03", "p04"],
  },
  p07: {
    procedureId: "p07",
    action: "부동산 소유권 이전(상속) 등기 방법을 확인하세요.",
    deadline: "등기·취득세 신고 기한이 있습니다. (예시 문구 · 검증 필요)",
    risk: "신고 기한을 넘기면 가산세가 붙을 수 있습니다.",
    agency: "관할 등기소 · 시·군·구청(취득세)",
    documents: ["등기신청서", "가족관계 서류", "상속재산분할협의서(필요 시)", "취득세 영수증"],
    methods: ["등기소 방문 신청", "인터넷등기소 전자 신청"],
    exceptions: ["상속인이 여러 명이면 지분 표시 방법이 달라집니다."],
    contacts: ["관할 등기소"],
    officialLinks: [LINK_IROS],
    relatedProcedureIds: ["p05", "p08"],
  },
  p08: {
    procedureId: "p08",
    action: "상속세 신고 대상인지와 신고 방법을 확인하세요.",
    deadline: "상속개시일이 속한 달의 말일부터 6개월 이내로 안내됩니다. (예시 문구 · 검증 필요)",
    risk: "이 서비스는 세액을 계산하지 않습니다. 신고 대상 여부는 국세청 안내를 확인하세요.",
    agency: "관할 세무서 · 국세청",
    documents: ["상속세 과세표준 신고서", "재산·채무 증빙", "가족관계 서류"],
    methods: ["홈택스 전자 신고", "관할 세무서 방문 신고"],
    exceptions: ["고인 또는 상속인이 해외에 있으면 기한이 달라질 수 있습니다."],
    contacts: ["국세상담센터 126"],
    officialLinks: [LINK_HOMETAX, LINK_LAW],
    relatedProcedureIds: ["p03", "p07"],
  },
}

export const findProcedureName = (procedureId: ProcedureId): string =>
  MOCK_PROCEDURE_SUMMARIES.find((item) => item.procedureId === procedureId)?.name ?? procedureId
