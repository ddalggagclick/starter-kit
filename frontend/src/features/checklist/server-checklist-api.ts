/*
 * 담당: [A] | 책임: A17 서버 체크리스트 조회·저장·삭제 호출(Mock / 실제 Backend 전환)과 itemStates 변환.
 * PRD: 태스크 4-5-3, 4-6-1, 4-6-2(소비 쪽), 4-3-4(서버). 계약: A17 GET·PUT·DELETE /api/me/checklist
 *   (x-confirmed: false, 경로 제안, Backend 라우터 없음 → 실제 모드는 실패로 처리된다).
 * 구현: VITE_USE_MOCK_API=false면 공통 Axios(Access Token·CSRF·401 Refresh 적용)로 계약 경로를 부르고, 아니면 Mock을 쓴다.
 *   GET 403(서버 저장 동의 없음)은 오류가 아니라 "동의 없음"으로 돌려준다.
 * 계약 없음: itemStates 안쪽 모양. 이 기기 저장과 같은 체크리스트 묶음을 한 객체로 넣는 제안 형태이며,
 *   변환은 toItemStates·fromItemStates 두 함수에만 둔다(계약 확정 시 여기만 고친다).
 * 제한사항: 동의 확인·요청 차단은 호출하는 쪽(server-checklist.ts) 책임이다. 서버 기록을 이 기기 기록과 합치지 않는다.
 */
import {
  deleteMyChecklist as deleteMyChecklistMock,
  getMyChecklist as getMyChecklistMock,
  putMyChecklist as putMyChecklistMock,
} from "@/mocks/mock-api"
import type { ChecklistSaved } from "@/mocks/wire-types"
import { toApiFailure } from "@/shared/api/api-error"
import { loadApiClient, USE_MOCK_API } from "@/shared/api/data-source"
import type { InitialAnswers, ProcedureId, RiskAnswer, RiskId } from "@/shared/contracts/domain"
import type { ProcedureState } from "@/shared/state/inheritance-store"
import type { ChecklistSnapshot } from "@/shared/storage/db"

const ITEM_KIND = "inheritance-checklist"
const ITEM_VERSION = 1

type ChecklistItemState = {
  kind: typeof ITEM_KIND
  version: typeof ITEM_VERSION
  answers: InitialAnswers | null
  riskAnswers: Partial<Record<RiskId, RiskAnswer>>
  procedureStates: Partial<Record<ProcedureId, ProcedureState>>
}

export const toItemStates = (snapshot: ChecklistSnapshot | null): object[] =>
  snapshot
    ? [
        {
          kind: ITEM_KIND,
          version: ITEM_VERSION,
          answers: snapshot.answers,
          riskAnswers: snapshot.riskAnswers,
          procedureStates: snapshot.procedureStates,
        } satisfies ChecklistItemState,
      ]
    : []

// 서버 값이 알아볼 수 없는 모양이면 null(지어내지 않는다).
export const fromItemStates = (itemStates: unknown): ChecklistSnapshot | null => {
  if (!Array.isArray(itemStates)) return null
  const item = itemStates.find(
    (entry): entry is ChecklistItemState =>
      typeof entry === "object" &&
      entry !== null &&
      (entry as { kind?: unknown }).kind === ITEM_KIND,
  )
  if (!item?.answers) return null
  return {
    answers: item.answers,
    riskAnswers: item.riskAnswers ?? {},
    procedureStates: (item.procedureStates ?? {}) as ChecklistSnapshot["procedureStates"],
  }
}

export type ServerChecklistRead = { consent: boolean; snapshot: ChecklistSnapshot | null }

export type ServerChecklistApi = {
  read: () => Promise<ServerChecklistRead>
  save: (snapshot: ChecklistSnapshot | null) => Promise<void>
  remove: () => Promise<void>
}

const NO_CONSENT: ServerChecklistRead = { consent: false, snapshot: null }

const fromSaved = (saved: Partial<ChecklistSaved> | undefined): ServerChecklistRead =>
  saved?.serverSaveConsent
    ? { consent: true, snapshot: fromItemStates(saved.itemStates) }
    : NO_CONSENT

// accountId: 로그인 계정. 요청은 그 계정 것으로만 보낸다(Mock은 계정 ID로 서버 기록을 나눈다).
export const serverChecklistApiFor = (accountId: string): ServerChecklistApi => {
  if (USE_MOCK_API) {
    return {
      read: async () => {
        try {
          return fromSaved(await getMyChecklistMock(accountId))
        } catch (error) {
          if (toApiFailure(error).status === 403) return NO_CONSENT
          throw error
        }
      },
      save: async (snapshot) => {
        await putMyChecklistMock(accountId, {
          itemStates: toItemStates(snapshot),
          serverSaveConsent: true,
        })
      },
      remove: async () => {
        await deleteMyChecklistMock(accountId)
      },
    }
  }
  return {
    read: async () => {
      const api = await loadApiClient()
      try {
        const response = await api.get<Partial<ChecklistSaved>>("/api/me/checklist")
        return fromSaved(response.data)
      } catch (error) {
        if (toApiFailure(error).status === 403) return NO_CONSENT
        throw error
      }
    },
    save: async (snapshot) => {
      const api = await loadApiClient()
      await api.put("/api/me/checklist", {
        itemStates: toItemStates(snapshot),
        serverSaveConsent: true,
      })
    },
    remove: async () => {
      const api = await loadApiClient()
      await api.delete("/api/me/checklist")
    },
  }
}
