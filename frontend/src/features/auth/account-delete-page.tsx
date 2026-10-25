/*
 * 담당: [A] | 책임: 회원 탈퇴 화면 /account/delete.
 * PRD: E5 / 태스크 5-4-1, 5-4-3. 계약: A16 DELETE /api/account {password} (x-confirmed: true, 경로 제안).
 *   성공 응답 본문 모양은 openapi에 없다(계약 없음) — 200 상태만 성공으로 본다.
 * 구현: 비밀번호 재확인과 확인 체크 후 요청한다. ① 서버 삭제 성공 확인 → ② 이 기기의 그 계정 기록(체크리스트·대화·동의) 삭제
 *   → ③ 로그아웃. ②가 실패하면 '완료'라고 하지 않고 남은 기록을 알린 뒤 재시도를 제공한다.
 * 제한사항: 다른 기기의 기록과 서버 백업은 즉시 지워졌다고 보장하지 않는다(정책 T15·T16). 비밀번호를 저장하지 않는다.
 */
import { type FormEvent, useId, useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import { toApiFailure } from "@/shared/api/api-error"
import { deleteAllNamespaceData } from "@/shared/storage/consent"
import { inheritanceDb, type StorageNamespace } from "@/shared/storage/db"
import { deleteAccountRequest, logoutRequest } from "./auth-api"
import { AuthCard, AuthField } from "./auth-form-field"
import { selectNamespace, useAuthStore } from "./auth-store"

const LIMITS_NOTICE =
  "다른 기기에 저장된 기록과 서버 백업은 즉시 지워지지 않을 수 있습니다. 다른 기기는 다음에 접속할 때 정리됩니다."

type Phase =
  | { kind: "form" }
  | { kind: "done" }
  // 서버 계정은 삭제됐지만 이 기기의 기록을 지우지 못했다. 다시 시도할 영역을 기억한다.
  | { kind: "local-failed"; namespace: StorageNamespace }

export function AccountDeletePage() {
  const accountId = useAuthStore((s) => s.accountId)
  const signOut = useAuthStore((s) => s.signOut)
  const [password, setPassword] = useState("")
  const [confirmed, setConfirmed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [phase, setPhase] = useState<Phase>({ kind: "form" })
  const confirmId = useId()

  const finishLocal = async (namespace: StorageNamespace) => {
    const result = await deleteAllNamespaceData(inheritanceDb, namespace)
    setPhase(result.ok ? { kind: "done" } : { kind: "local-failed", namespace })
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!password || !confirmed) {
      setError("비밀번호를 입력하고 탈퇴 안내를 확인해 주세요.")
      return
    }
    const namespace = selectNamespace(useAuthStore.getState())
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
    // 서버 계정 삭제가 확인된 뒤에만 이 기기 기록을 지우고 로그아웃한다.
    await finishLocal(namespace)
    void logoutRequest()
    signOut()
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
            await finishLocal(phase.namespace)
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
