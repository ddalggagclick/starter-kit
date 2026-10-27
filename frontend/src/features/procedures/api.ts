/*
 * 담당: [A] | 책임: A07 절차 목록·상세 조회 훅(W-02·W-03·W-04 공용).
 * PRD: 태스크 2-2-1, 2-2-3, 2-3-1, 7-1-3. API: A07 GET /api/procedures, /api/procedures/{procedureId}
 *   (openapi 0.2.1 x-confirmed: true, 경로 확정).
 * 구현: VITE_USE_MOCK_API=false면 공통 Axios로 실제 Backend를, 아니면 Mock(src/mocks)을 쓴다. TanStack Query로 캐시한다.
 * 제한사항: 생성 타입은 모든 필드가 선택이라 화면용 타입으로 정규화한다. 빠진 값을 지어내지 않고 빈 값으로 둔다.
 *   절차 문구·기한은 B3 검수 대상이다.
 */
import { useQuery } from "@tanstack/react-query"
import { getProcedure, listProcedures } from "@/mocks/mock-api"
import { loadApiClient, USE_MOCK_API } from "@/shared/api/data-source"
import type { operations } from "@/shared/api/schema"
import type { ProcedureDetailWire } from "@/shared/api/types"
import type { ProcedureId } from "@/shared/contracts/domain"
import type { ProcedureDetail, ProcedureListResponse } from "@/shared/contracts/procedure"

type ProcedureListWire =
  operations["A07_listProcedures"]["responses"][200]["content"]["application/json"]

// 절차 ID가 없는 항목은 이동할 곳이 없어 버린다. 나머지 빈 칸은 빈 문자열로 둔다.
export const normalizeProcedureList = (wire: ProcedureListWire): ProcedureListResponse => ({
  procedures: (wire.procedures ?? []).flatMap((item) =>
    item.procedureId
      ? [{ procedureId: item.procedureId, name: item.name ?? "", summary: item.summary ?? "" }]
      : [],
  ),
})

// url이 없는 공식 링크는 버린다. 화면이 빈 링크를 만들지 않게 한다.
export const normalizeProcedureDetail = (
  procedureId: ProcedureId,
  wire: ProcedureDetailWire,
): ProcedureDetail => ({
  procedureId: wire.procedureId ?? procedureId,
  action: wire.action ?? "",
  deadline: wire.deadline ?? "",
  risk: wire.risk ?? "",
  agency: wire.agency ?? "",
  documents: wire.documents ?? [],
  methods: wire.methods ?? [],
  exceptions: wire.exceptions ?? [],
  contacts: wire.contacts ?? [],
  officialLinks: (wire.officialLinks ?? []).flatMap((link) =>
    link.url ? [{ title: link.title ?? link.url, url: link.url }] : [],
  ),
  relatedProcedureIds: wire.relatedProcedureIds ?? [],
})

const fetchProcedureList = async (signal: AbortSignal): Promise<ProcedureListResponse> => {
  if (USE_MOCK_API) return listProcedures({ signal })
  const api = await loadApiClient()
  const response = await api.get<ProcedureListWire>("/api/procedures", { signal })
  return normalizeProcedureList(response.data)
}

const fetchProcedureDetail = async (
  procedureId: string,
  signal: AbortSignal,
): Promise<ProcedureDetail> => {
  if (USE_MOCK_API) return getProcedure(procedureId, { signal })
  const api = await loadApiClient()
  // 주소창에서 온 값이라 인코딩한다. p01~p08이 아니면 서버가 422로 거부한다.
  const response = await api.get<ProcedureDetailWire>(
    `/api/procedures/${encodeURIComponent(procedureId)}`,
    { signal },
  )
  return normalizeProcedureDetail(procedureId as ProcedureId, response.data)
}

export const useProcedureList = () =>
  useQuery({
    queryKey: ["procedures"],
    queryFn: ({ signal }) => fetchProcedureList(signal),
    staleTime: Number.POSITIVE_INFINITY,
  })

export const useProcedureDetail = (procedureId: string) =>
  useQuery({
    queryKey: ["procedures", procedureId],
    queryFn: ({ signal }) => fetchProcedureDetail(procedureId, signal),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  })

export const procedureNumber = (procedureId: ProcedureId) => Number(procedureId.slice(1))
