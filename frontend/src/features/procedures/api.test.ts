// A07 실제 응답 정규화 테스트: 선택 필드가 빠져도 화면용 타입을 채우고, 빈 링크·ID 없는 항목을 만들지 않는다.
import { describe, expect, it } from "vitest"
import { normalizeProcedureDetail, normalizeProcedureList } from "./api"

describe("normalizeProcedureList", () => {
  it("절차 ID가 없는 항목은 버리고, 빠진 이름·요약은 빈 문자열로 둔다", () => {
    expect(
      normalizeProcedureList({
        procedures: [{ procedureId: "p01", name: "사망 신고" }, { name: "ID 없음" }],
      }),
    ).toEqual({ procedures: [{ procedureId: "p01", name: "사망 신고", summary: "" }] })
  })

  it("procedures가 없으면 빈 목록이다", () => {
    expect(normalizeProcedureList({})).toEqual({ procedures: [] })
  })
})

describe("normalizeProcedureDetail", () => {
  it("빠진 칸은 빈 값으로 채우고 url 없는 공식 링크는 버린다", () => {
    const detail = normalizeProcedureDetail("p05", {
      action: "가정법원 신고",
      officialLinks: [{ title: "대법원", url: "https://help.scourt.go.kr" }, { title: "url 없음" }],
    })

    expect(detail).toEqual({
      procedureId: "p05",
      action: "가정법원 신고",
      deadline: "",
      risk: "",
      agency: "",
      documents: [],
      methods: [],
      exceptions: [],
      contacts: [],
      officialLinks: [{ title: "대법원", url: "https://help.scourt.go.kr" }],
      relatedProcedureIds: [],
    })
  })
})
