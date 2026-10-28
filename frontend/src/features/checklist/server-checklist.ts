/*
 * 담당: [A] | 책임: 로그인 사용자의 서버 체크리스트 저장 동의·저장·불러오기·철회 상태(A17).
 * PRD: E4 / 태스크 4-5-1, 4-6-1, 4-5-3, 4-6-3, 4-3-4(서버). 정책 S01-B·S02·S06-B·T13-A·T14-A.
 * 구현:
 *   - 비로그인이면 서버 요청을 하나도 보내지 않는다. 로그인하면 그 계정의 동의 상태를 조회(GET)만 한다.
 *     체크리스트 데이터를 보내는 요청(PUT·DELETE)은 서버 저장 동의 뒤에만 보낸다(4-6-1).
 *   - 서버에 기록이 있으면 화면·기기 기록과 자동으로 합치지 않는다. 사용자가 [서버 기록 불러오기] 또는
 *     [이 기기 내용으로 서버 덮어쓰기]를 고를 때까지 서버 자동 저장을 멈춘다(4-6-3, S06-B).
 *   - 저장 실패는 서버 상태만 '실패'로 두고 화면·기기 상태는 그대로 둔다. [다시 시도]로 다시 보낸다(T13-A).
 *   - 서버 저장 철회(DELETE)가 실패하면 서버에 기록이 남았다고 알리고 서버만 다시 시도한다(T14-A, 검증 ②).
 *   - 모든 동작은 요청한 계정이 지금 실행 중일 때만 실행한다(다른 계정 요청 차단). 저장·삭제는 순서 큐에서 처리한다.
 * 제한사항: 이 기기 저장(checklist-storage.ts)과 동의·삭제가 따로다. A17은 계약 미확정·Backend 미구현이라 Mock으로만 검증했다.
 */
import { useEffect } from "react"
import { create } from "zustand"
import { useAuthStore } from "@/features/auth/auth-store"
import { useInheritanceStore } from "@/shared/state/inheritance-store"
import type { ChecklistSnapshot } from "@/shared/storage/db"
import { type ServerChecklistApi, serverChecklistApiFor } from "./server-checklist-api"

// checking: 동의 상태 조회 중, unknown: 조회 실패, none: 동의 없음, granted: 동의함
export type ServerConsent = "off" | "checking" | "unknown" | "none" | "granted"
export type ServerSaveStatus = "idle" | "saving" | "saved" | "failed"
export type ServerRevokeResult = { ok: boolean } | null

type ServerChecklistState = {
  accountId: string | null
  consent: ServerConsent
  saveStatus: ServerSaveStatus
  // 서버에 있던 기록. 사용자가 고르기 전까지 자동 저장을 멈춘다.
  pending: ChecklistSnapshot | null
  declined: boolean
  revokeResult: ServerRevokeResult
}

const INITIAL: Omit<ServerChecklistState, "accountId"> = {
  consent: "off",
  saveStatus: "idle",
  pending: null,
  declined: false,
  revokeResult: null,
}

export const useServerChecklistStore = create<ServerChecklistState>()(() => ({
  accountId: null,
  ...INITIAL,
}))

const patch = (next: Partial<ServerChecklistState>) => useServerChecklistStore.setState(next)

const snapshotOf = (): ChecklistSnapshot | null => {
  const { answers, riskAnswers, procedureStates } = useInheritanceStore.getState()
  return answers ? { answers, riskAnswers, procedureStates } : null
}

type ActiveSync = {
  accountId: string
  check: () => Promise<void>
  grant: () => Promise<boolean>
  retrySave: () => Promise<void>
  loadPending: () => void
  keepLocal: () => Promise<void>
  revoke: () => Promise<boolean>
}
let activeSync: ActiveSync | null = null

export type ServerChecklistSync = {
  ready: Promise<void>
  flush: () => Promise<void>
  stop: () => void
}

// 로그인 계정이 정해지면 시작한다. 계정이 바뀌면 stop 후 다시 시작한다. 비로그인(null)이면 아무 요청도 하지 않는다.
export const startServerChecklistSync = (
  accountId: string | null,
  api: ServerChecklistApi | null = accountId ? serverChecklistApiFor(accountId) : null,
): ServerChecklistSync => {
  let active = true
  let queue: Promise<void> = Promise.resolve()
  patch({ accountId, ...INITIAL, consent: accountId ? "checking" : "off" })

  if (!accountId || !api) {
    return { ready: Promise.resolve(), flush: () => Promise.resolve(), stop: () => {} }
  }

  const isCurrent = () => active && useServerChecklistStore.getState().accountId === accountId
  const canAutoSave = () => {
    const { consent, pending } = useServerChecklistStore.getState()
    return consent === "granted" && pending === null
  }

  const runInQueue = <T>(task: () => Promise<T>): Promise<T> => {
    const run = queue.then(task)
    queue = run.then(
      () => undefined,
      () => undefined,
    )
    return run
  }

  // 그 순간의 최신 화면 상태를 서버에 저장한다. 결과로만 '저장됨'을 표시한다.
  // 화면이 비워진 것(이 기기 기록 삭제·철회로 초기화)은 서버로 보내지 않는다. 보내면 서버 기록이 빈 값으로
  // 덮어써져 이 기기·서버 삭제가 섞인다. 서버 기록은 [서버 저장 철회]로만 지운다(검증 ②).
  const save = () =>
    runInQueue(async () => {
      if (!isCurrent() || !canAutoSave()) return
      const snapshot = snapshotOf()
      if (!snapshot) return
      patch({ saveStatus: "saving" })
      try {
        await api.save(snapshot)
        if (isCurrent()) patch({ saveStatus: "saved" })
      } catch {
        if (isCurrent()) patch({ saveStatus: "failed" })
      }
    })

  const unsubscribe = useInheritanceStore.subscribe((state, previous) => {
    if (!canAutoSave()) return
    const changed =
      state.answers !== previous.answers ||
      state.riskAnswers !== previous.riskAnswers ||
      state.procedureStates !== previous.procedureStates
    if (changed) void save()
  })

  // 동의 상태 조회(GET). 서버 기록이 있으면 고를 때까지 보류한다.
  const check = () =>
    runInQueue(async () => {
      patch({ consent: "checking" })
      try {
        const read = await api.read()
        if (!isCurrent()) return
        patch({
          consent: read.consent ? "granted" : "none",
          pending: read.consent ? read.snapshot : null,
          saveStatus: read.consent ? "saved" : "idle",
        })
      } catch {
        if (isCurrent()) patch({ consent: "unknown" })
      }
    })

  // 사용자가 서버 저장 정책을 확인하고 [서버에 저장]을 눌렀을 때만 호출한다(4-6-1).
  // 보낼 답이 없으면(질문에 답하기 전, 이 기기 기록 삭제 직후) 보내지 않는다. 서버에 빈 기록을 만들지 않는다(리뷰 반영).
  const grant = () =>
    runInQueue(async () => {
      if (!isCurrent()) return false
      const snapshot = snapshotOf()
      if (!snapshot) return false
      patch({ saveStatus: "saving", revokeResult: null })
      try {
        await api.save(snapshot)
        if (!isCurrent()) return false
        patch({ consent: "granted", pending: null, saveStatus: "saved", declined: false })
        return true
      } catch {
        if (isCurrent()) patch({ saveStatus: "failed" })
        return false
      }
    })

  const loadPending = () => {
    const { pending } = useServerChecklistStore.getState()
    if (!isCurrent() || !pending) return
    useInheritanceStore.getState().replaceWithSaved(pending)
    patch({ pending: null })
  }

  // 사용자가 [이 기기 내용으로 서버 덮어쓰기]를 골랐을 때. 보류를 풀고 지금 화면 상태를 저장한다.
  // 덮어쓸 답이 없으면 보류를 그대로 둔다(서버 기록을 고를 기회를 남긴다).
  const keepLocal = async () => {
    if (!isCurrent() || !snapshotOf()) return
    patch({ pending: null })
    await save()
  }

  // 서버 저장 철회(DELETE = 동의 철회 + 서버 기록 삭제). 실패하면 서버 기록이 남은 것으로 알린다.
  const revoke = () =>
    runInQueue(async () => {
      if (!isCurrent()) return false
      try {
        await api.remove()
        if (!isCurrent()) return false
        patch({ consent: "none", pending: null, saveStatus: "idle", revokeResult: { ok: true } })
        return true
      } catch {
        if (isCurrent()) patch({ revokeResult: { ok: false } })
        return false
      }
    })

  const self: ActiveSync = {
    accountId,
    check,
    grant,
    retrySave: save,
    loadPending,
    keepLocal,
    revoke,
  }
  activeSync = self

  return {
    ready: check(),
    flush: () => queue,
    stop: () => {
      active = false
      unsubscribe()
      if (activeSync === self) activeSync = null
    },
  }
}

// 요청한 계정이 지금 실행 중일 때만 돌려준다. 계정이 바뀌었으면 다른 계정 요청을 막도록 null.
const syncFor = (accountId: string) => (activeSync?.accountId === accountId ? activeSync : null)

export const grantServerSave = (accountId: string): Promise<boolean> =>
  syncFor(accountId)?.grant() ?? Promise.resolve(false)
export const retryServerSave = (accountId: string): Promise<void> =>
  syncFor(accountId)?.retrySave() ?? Promise.resolve()
export const recheckServerSave = (accountId: string): Promise<void> =>
  syncFor(accountId)?.check() ?? Promise.resolve()
export const loadServerRecord = (accountId: string) => syncFor(accountId)?.loadPending()
export const keepLocalOverServer = (accountId: string): Promise<void> =>
  syncFor(accountId)?.keepLocal() ?? Promise.resolve()
export const revokeServerSave = (accountId: string): Promise<boolean> =>
  syncFor(accountId)?.revoke() ?? Promise.resolve(false)
export const declineServerSave = () => patch({ declined: true })

// 앱 레이아웃에서 로그인 계정에 맞춰 시작·정지한다.
export const useServerChecklistSync = () => {
  const accountId = useAuthStore((s) => s.accountId)
  useEffect(() => {
    const sync = startServerChecklistSync(accountId)
    return sync.stop
  }, [accountId])
}
