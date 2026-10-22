/*
 * 담당: [A] | 책임: A07 절차 목록·상세 조회 훅(W-02·W-03·W-04 공용).
 * PRD: 태스크 2-2-1, 2-2-3, 2-3-1. API: A07 GET /api/procedures, /api/procedures/{procedureId} (x-confirmed: false).
 * 구현: TanStack Query로 캐시한다. Backend에 A07 라우터가 없어 V1은 Mock(src/mocks)을 쓴다.
 * 제한사항: 절차 이름·문구·기한은 B3 검수 전 예시다. 경로가 확정되면 Axios 호출로 바꾼다.
 */
import { useQuery } from "@tanstack/react-query"
import { getProcedure, listProcedures } from "@/mocks/mock-api"
import type { ProcedureId } from "@/shared/contracts/domain"

export const useProcedureList = () =>
  useQuery({
    queryKey: ["procedures"],
    queryFn: ({ signal }) => listProcedures({ signal }),
    staleTime: Number.POSITIVE_INFINITY,
  })

export const useProcedureDetail = (procedureId: string) =>
  useQuery({
    queryKey: ["procedures", procedureId],
    queryFn: ({ signal }) => getProcedure(procedureId, { signal }),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  })

export const procedureNumber = (procedureId: ProcedureId) => Number(procedureId.slice(1))
