# 담당: [B] | 책임: 8개 고정 절차의 추천 규칙.
# PRD: E1 / 스토리 1-1 / 태스크 1-1-3; E2 / 스토리 2-2 / 태스크 2-2-2.
# 구현할 기능: 같은 입력과 규칙 버전에 같은 추천·이유를 반환하고 입력 후보 8개를 최대 5개로 제한한다.
# 완료 기준: 추천 수·규칙 버전·선정 이유가 결과에 포함된다.
# 제한사항: 추천 순서는 법적 의무나 개인별 법률 판단을 뜻하지 않는다. 카카오와 웹은 이 규칙을 공유한다.
# 상태: PRD 태스크 미시작.
"""공통 8개 절차 안내 규칙과 사전 승인 문구.

문구 원문은 '체크리스트 조건별 안내문구 공식자료 검증 Q98' 8장(설계 기준선 v1.0)을 그대로 옮긴다.
이 파일에서 새 문장을 만들지 않는다. 문구를 바꿀 때는 원문 문서를 먼저 고치고 CONTENT_VERSION을 올린다.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from inheritance.contracts.domain import (
    AnswerChoice,
    InitialAnswers,
    ProcedureId,
    RiskAnswer,
    RiskId,
)

CONTENT_VERSION = "q98-baseline-v1.0"

# 결정 문서 2.2절의 고정 순서(Q86·Q87). 정보 탐색용 순서이며 법적 우선순위가 아니다.
PROCEDURE_ORDER: tuple[ProcedureId, ...] = (
    "p01",
    "p02",
    "p03",
    "p04",
    "p05",
    "p06",
    "p07",
    "p08",
)
PROCEDURE_TITLES: MappingProxyType[ProcedureId, str] = MappingProxyType(
    {
        "p01": "사망 관련 행정",
        "p02": "상속인·가족관계 확인",
        "p03": "안심상속 원스톱서비스",
        "p04": "재산·채무 확인",
        "p05": "상속포기·한정승인",
        "p06": "금융재산 후속 절차",
        "p07": "부동산 상속",
        "p08": "고인 명의 휴대전화",
    }
)

CARD_TEXTS: MappingProxyType[str, str] = MappingProxyType(
    {
        "01": "사망 관련 신고·처리 상태를 확인하세요.",
        "02": "고인의 사망일과 신고 상태를 확인하세요.",
        "03": "안심상속 신청 후 조회 결과를 확인하는 방법을 살펴보세요.",
        "04": "신청 가능 여부와 신청 방법을 확인하세요.",
        "05": "안심상속 신청 여부를 먼저 확인하세요.",
        "06": "재산·채무 조회 결과의 제공 여부와 확인 범위를 살펴보세요.",
        "07": "공식 재산·채무 조회 방법과 확인 항목을 살펴보세요.",
        "08": "재산·채무를 확인할 수 있는 공식 조회 경로를 살펴보세요.",
        "09": "신청 기간 판단에 필요한 사실과 공식 안내를 확인하세요.",
        "10": "사망일과 본인의 상속개시 사실 인지 시점 등 기간 판단에 필요한 사항을 확인하세요.",
    }
)

WARNING_TEXTS: MappingProxyType[str, str] = MappingProxyType(
    {
        "W00": (
            "상속포기·한정승인은 신청 기간이 있는 절차입니다. 신고 방법은 공식 법원 안내에서 "
            "확인하고, 본인에게 적용되는 기간은 대한법률구조공단에 상담하세요."
        ),
        "W01": (
            "고인의 재산·채무를 확인할 수 있는 공식 조회 방법을 살펴보세요. 본인의 채무 부담 "
            "여부는 대한법률구조공단에 상담하세요."
        ),
        "W02": (
            "사망 후 고인의 재산이 처분되거나 사용됐다면 누가, 언제, 무엇을 했는지 확인하세요. "
            "법적 영향은 대한법률구조공단에 상담하세요."
        ),
        "W03": (
            "본인에 관한 상속포기·한정승인 신고 여부와 법원 처리 상태를 확인하세요. 신고의 법적 "
            "효력에 관한 상담은 대한법률구조공단을 이용하세요."
        ),
    }
)
COMMON_WARNING_ID = "W00"
RISK_WARNING_IDS: MappingProxyType[RiskId, str] = MappingProxyType(
    {"debt": "W01", "property_disposal": "W02", "self_application": "W03"}
)

# 위험 답변별 W01~W03 노출 조건. 결정 문서 22.2절이 개발자의 임의 기본값을 금지한다.
# TODO(B1 김현주, PRD 1-2-2): 팀이 노출 조건을 확정하면 예: {"debt": frozenset({"yes"})} 형태로 채운다.
# 비어 있는 동안은 PRD 1-2-4에 따라 공통 경고와 웹 링크만 반환한다.
RISK_WARNING_EXPOSURE: MappingProxyType[RiskId, frozenset[AnswerChoice]] = MappingProxyType({})


@dataclass(frozen=True)
class SourceLink:
    title: str
    url: str
    # Q98 8.3 링크 정책: 데모 배포 전 실제 브라우저 접근 확인이 끝나면 True로 바꾼다.
    browser_checked: bool = False


@dataclass(frozen=True)
class FallbackNotice:
    fallback_id: str
    text: str
    links: tuple[SourceLink, ...]
    caution: str | None = None


# 아래 링크 7개는 2026-10-21 브라우저 확인 완료(PRD 1-3-2). 새 링크는 확인 전까지 기본값 False로 둔다.
_GOV24 = SourceLink("정부24", "https://www.gov.kr/", browser_checked=True)
_ONE_STOP = SourceLink(
    "정부24 안심상속",
    "https://www.gov.kr/mw/AA020InfoCappView.do?CappBizCD=17400000001",
    browser_checked=True,
)
FALLBACKS: MappingProxyType[str, FallbackNotice] = MappingProxyType(
    {
        "F01": FallbackNotice(
            "F01",
            "사망신고의 절차와 구비서류를 정부24 또는 관할 접수기관에서 확인하세요.",
            (
                SourceLink(
                    "정부24 사망신고",
                    "https://www.gov.kr/mw/AA020InfoCappView.do"
                    "?CappBizCD=12700000059&HighCtgCD=A09006",
                    browser_checked=True,
                ),
                _GOV24,
            ),
        ),
        "F02": FallbackNotice(
            "F02",
            "안심상속 신청 방법과 필요 서류를 정부24에서 확인하세요.",
            (_ONE_STOP, _GOV24),
        ),
        "F03": FallbackNotice(
            "F03",
            "재산·채무 조회 대상과 결과 확인 방법을 국세청의 공식 안내에서 확인하세요.",
            (
                SourceLink(
                    "국세청 상속재산의 확인",
                    "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7725&mi=2332",
                    browser_checked=True,
                ),
                _ONE_STOP,
                SourceLink("국세청", "https://www.nts.go.kr/", browser_checked=True),
            ),
            caution=(
                "공식 조회에 포함되지 않는 재산·채무가 있을 수 있습니다. 조회 결과만으로 모든 "
                "재산·채무를 확인했다고 판단하지 마세요."
            ),
        ),
        "F04": FallbackNotice(
            "F04",
            "상속포기·한정승인 신고 절차와 서류는 법원 공식 안내에서 확인하세요.",
            (
                SourceLink(
                    "법원 전자민원센터",
                    "https://www.scourt.go.kr/nm/main/index.html",
                    browser_checked=True,
                ),
                SourceLink("대한법률구조공단", "https://www.klac.or.kr/", browser_checked=True),
            ),
            caution="본인에게 적용되는 법적 기한이나 효력은 대한법률구조공단에서 상담하세요.",
        ),
    }
)
PROCEDURE_FALLBACK_IDS: MappingProxyType[ProcedureId, str] = MappingProxyType(
    {"p01": "F01", "p03": "F02", "p04": "F03", "p05": "F04"}
)


@dataclass(frozen=True)
class ProcedureNotice:
    procedure_id: ProcedureId
    title: str
    card_id: str | None
    card_text: str | None
    fallback: FallbackNotice | None


@dataclass(frozen=True)
class RiskNotice:
    risk_id: RiskId
    answer: AnswerChoice
    confirmed: bool
    warning_id: str | None
    warning_text: str | None


@dataclass(frozen=True)
class RiskInformation:
    common_warning_id: str
    common_warning_text: str
    answered: tuple[RiskNotice, ...]


# 사망일 상태와 안심상속 자기신고 값으로 조건 카드를 고른다. 상속인 자격·기한은 판단하지 않는다.
# 카드가 없는 절차(p02·p06·p07·p08)는 상세 명세가 승인될 때까지 None이다.
def select_card_id(procedure_id: ProcedureId, initial: InitialAnswers) -> str | None:
    if procedure_id == "p01":
        return "02" if initial.death_date_unknown else "01"
    if procedure_id == "p03":
        return {"yes": "03", "no": "04", "unknown": "05"}[initial.one_stop_application]
    if procedure_id == "p04":
        return {"yes": "06", "no": "07", "unknown": "08"}[initial.one_stop_application]
    if procedure_id == "p05":
        return "10" if initial.death_date_unknown else "09"
    return None


# 입력과 무관하게 8개 절차를 고정 순서로 모두 돌려준다. 답변은 문구만 바꾼다.
def build_procedure_notices(initial: InitialAnswers) -> tuple[ProcedureNotice, ...]:
    notices = []
    for procedure_id in PROCEDURE_ORDER:
        card_id = select_card_id(procedure_id, initial)
        fallback_id = PROCEDURE_FALLBACK_IDS.get(procedure_id)
        notices.append(
            ProcedureNotice(
                procedure_id=procedure_id,
                title=PROCEDURE_TITLES[procedure_id],
                card_id=card_id,
                card_text=CARD_TEXTS[card_id] if card_id else None,
                fallback=FALLBACKS[fallback_id] if fallback_id else None,
            )
        )
    return tuple(notices)


# 답한 위험 질문만 담고 답변 값(yes/no/unknown)을 그대로 보존한다. 답하지 않은 질문은 넣지 않는다.
# 노출 조건이 승인되지 않은 답변은 개별 경고 없이 공통 경고만 받는다(PRD 1-2-4).
def build_risk_information(
    risks: tuple[RiskAnswer, ...],
    exposure: MappingProxyType[RiskId, frozenset[AnswerChoice]] = RISK_WARNING_EXPOSURE,
) -> RiskInformation:
    answered = []
    for risk in sorted(risks, key=lambda item: tuple(RISK_WARNING_IDS).index(item.risk_id)):
        warning_id = None
        if risk.answer in exposure.get(risk.risk_id, frozenset()):
            warning_id = RISK_WARNING_IDS[risk.risk_id]
        answered.append(
            RiskNotice(
                risk_id=risk.risk_id,
                answer=risk.answer,
                confirmed=risk.confirmed,
                warning_id=warning_id,
                warning_text=WARNING_TEXTS[warning_id] if warning_id else None,
            )
        )
    return RiskInformation(
        common_warning_id=COMMON_WARNING_ID,
        common_warning_text=WARNING_TEXTS[COMMON_WARNING_ID],
        answered=tuple(answered),
    )
