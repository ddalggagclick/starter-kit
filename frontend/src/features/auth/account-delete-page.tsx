/*
 * 담당: [A] | 책임: 회원 탈퇴 화면 /account/delete.
 * PRD: E5 / 태스크 5-4-1, 5-4-3. 계약: A16 DELETE /api/account {password} (x-confirmed: true, 경로 제안).
 *   성공 응답 본문 모양은 openapi에 없다(계약 없음) — 200 상태만 성공으로 본다.
 * 구현: 비밀번호 재확인과 확인 체크 후 요청한다. ① 서버 삭제 성공 확인 → ② 이 기기의 그 계정 기록(체크리스트·대화·동의) 삭제
 *   → ③ 로그아웃. ②가 실패하면 로그아웃하지 않고 '완료'라고 하지도 않는다. 남은 기록을 알린 뒤 재시도를 제공하고,
 *   재시도로 ②가 성공해야 ③을 한다(재시도가 같은 계정 흐름에 묶이도록).
 *   ③은 탈퇴를 요청한 계정·세션이 아직 이 탭에 로그인돼 있을 때만 한다. 그 사이 다른 계정으로 로그인했으면 건드리지 않는다.
 *   서버 세션은 탈퇴로 이미 삭제되므로 서버 로그아웃 요청은 보내지 않는다(새로 로그인한 계정의 쿠키를 끊지 않도록).
 * 제한사항: 이 기기 기록만 지운다. 다른 기기 기록을 지우는 기능은 없고(T16 미구현) 서버 백업 삭제도 보장하지 않는다.
 *   비밀번호를 저장하지 않는다.
 */
import { type FormEvent, useId, useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import { toApiFailure } from "@/shared/api/api-error"
import { accessSession } from "@/shared/api/auth"
import { deleteAllNamespaceData } from "@/shared/storage/consent"
import { inheritanceDb, type StorageNamespace } from "@/shared/storage/db"
import { deleteAccountRequest } from "./auth-api"
import { AuthCard, AuthField } from "./auth-form-field"
import { selectNamespace, useAuthStore } from "./auth-store"

// 다른 기기 기록은 자동으로 지워지지 않는다. 사실대로 안내한다.
const LIMITS_NOTICE =
  "이 기기의 기록만 삭제됩니다. 다른 기기(브라우저)에 저장한 기록은 자동으로 지워지지 않으니 그 기기에서 직접 삭제해 주세요. 서버 백업에서도 즉시 지워지지 않을 수 있습니다."

// 탈퇴를 요청한 계정과 그때의 세션 번호.
type DeleteTarget = { accountId: string; namespace: StorageNamespace; epoch: number }

type Phase =
  | { kind: "form" }
  | { kind: "done" }
  // 서버 계정은 삭제됐지만 이 기기의 기록을 지우지 못했다. 다시 시도할 대상을 기억한다.
  | { kind: "local-failed"; target: DeleteTarget }

export function AccountDeletePage() {
  const accountId = useAuthStore((s) => s.accountId)
  const signOut = useAuthStore((s) => s.signOut)
  const [password, setPassword] = useState("")
  const [confirmed, setConfirmed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [phase, setPhase] = useState<Phase>({ kind: "form" })
  const confirmId = useId()

  // ② 이 기기 기록 삭제 → 성공했을 때만 ③ 이 탭 로그아웃. 결과(성공 여부)를 돌려준다.
  const finishLocal = async (target: DeleteTarget): Promise<boolean> => {
    const result = await deleteAllNamespaceData(inheritanceDb, target.namespace)
    if (!result.ok) {
      setPhase({ kind: "local-failed", target })
      return false
    }
    // 탈퇴를 요청한 계정·세션이 그대로일 때만 로그아웃한다. 그 사이 B로 로그인했으면 B를 건드리지 않는다.
    const stillSameSession =
      useAuthStore.getState().accountId === target.accountId &&
      accessSession.isCurrent(target.epoch)
    if (stillSameSession) {
      accessSession.end()
      signOut()
    }
    setPhase({ kind: "done" })
    return true
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!password || !confirmed) {
      setError("비밀번호를 입력하고 탈퇴 안내를 확인해 주세요.")
      return
    }
    const auth = useAuthStore.getState()
    if (!auth.accountId) return
    const target: DeleteTarget = {
      accountId: auth.accountId,
      namespace: selectNamespace(auth),
      epoch: accessSession.current(),
    }
    setBusy(true)
    setError(null)
    try {
      await deleteAccountRequest(password)
    } catch (failure) {
      const { status } = toApiFailure(failure)
      if (status === 403) setError("비밀번호가 맞지 않습니다.")
      else if (status === 401) setError("로그인이 만료되었습니다. 다시 로그인한 뒤 시도해 주세요.")
      else setError("탈퇴하지 못했습니다. 잠시 후 다시 시도해 주세요.")
      setBusy(false)
      setPassword("")
      return
    }
    // 서버 계정 삭제가 확인된 뒤에만 이 기기 기록을 지운다. 로그아웃은 finishLocal이 삭제 성공 후에 한다.
    await finishLocal(target)
    setBusy(false)
    setPassword("")
  }

  if (phase.kind === "done") {
    return (
      <AuthCard title="회원 탈퇴">
        <Notice tone="success">탈퇴했습니다. 계정과 이 기기에 저장된 기록을 삭제했습니다.</Notice>
        <p className="text-sm text-muted-foreground">{LIMITS_NOTICE}</p>
        <Link to="/" className="text-sm underline underline-offset-4">
          첫 화면으로
        </Link>
      </AuthCard>
    )
  }

  if (phase.kind === "local-failed") {
    return (
      <AuthCard title="회원 탈퇴">
        <Notice tone="warning">
          계정은 삭제했지만 이 기기에 저장된 기록(체크리스트·AI 대화)을 지우지 못했습니다. 다시
          시도해 주세요.
        </Notice>
        <Button
          type="button"
          className="w-full"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            await finishLocal(phase.target)
            setBusy(false)
          }}
        >
          이 기기 기록 다시 삭제
        </Button>
        <p className="text-sm text-muted-foreground">{LIMITS_NOTICE}</p>
      </AuthCard>
    )
  }

  if (!accountId) {
    return (
      <AuthCard title="회원 탈퇴">
        <p className="text-sm">탈퇴하려면 먼저 로그인해 주세요.</p>
        <Button asChild className="w-full">
          <Link to="/login" state={{ from: "/account/delete" }}>
            로그인
          </Link>
        </Button>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="회원 탈퇴" description="탈퇴하면 계정과 로그인 기록을 되돌릴 수 없습니다.">
      <form className="space-y-4" onSubmit={onSubmit} noValidate>
        {error && <Notice tone="danger">{error}</Notice>}
        <AuthField
          label="비밀번호 확인"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
        />
        <div className="flex items-start gap-2 text-sm">
          <input
            id={confirmId}
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            className="mt-1"
          />
          <label htmlFor={confirmId}>
            탈퇴하면 계정과 이 기기에 저장된 이 계정의 기록이 삭제됨을 확인했습니다.
          </label>
        </div>
        <p className="text-xs text-muted-foreground">{LIMITS_NOTICE}</p>
        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>
            {busy ? "탈퇴 처리 중…" : "탈퇴하기"}
          </Button>
          <Button asChild type="button" variant="outline">
            <Link to="/">취소</Link>
          </Button>
        </div>
      </form>
    </AuthCard>
  )
}
