/*
 * 담당: [A] | 책임: 인증 메일 재전송 입력(가입 직후 화면·인증 실패 화면 공용).
 * PRD: 태스크 5-5-1. 계약: A12 POST /api/auth/email/resend {email} → 202, 429 RATE_LIMITED(60초 간격·하루 5회).
 * 구현: 가입 여부를 알리지 않으므로 성공하면 항상 같은 접수 문구를 보인다.
 */
import { type FormEvent, useState } from "react"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import { toApiFailure } from "@/shared/api/api-error"
import { resendVerificationRequest } from "./auth-api"
import { AuthField } from "./auth-form-field"

export function ResendVerificationForm({ initialEmail = "" }: { initialEmail?: string }) {
  const [email, setEmail] = useState(initialEmail)
  const [result, setResult] = useState<"sent" | "limited" | "error" | null>(null)
  const [sending, setSending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!email.trim()) return
    setSending(true)
    try {
      await resendVerificationRequest(email.trim())
      setResult("sent")
    } catch (error) {
      setResult(toApiFailure(error).status === 429 ? "limited" : "error")
    } finally {
      setSending(false)
    }
  }

  return (
    <form className="space-y-3" onSubmit={onSubmit} noValidate>
      <AuthField
        label="이메일"
        type="email"
        autoComplete="email"
        value={email}
        onChange={setEmail}
      />
      <Button
        type="submit"
        variant="outline"
        className="w-full"
        disabled={sending || !email.trim()}
      >
        인증 메일 다시 받기
      </Button>
      {result === "sent" && (
        <Notice tone="info">
          가입된 이메일이면 인증 메일을 다시 보냈습니다. 메일함을 확인해 주세요.
        </Notice>
      )}
      {result === "limited" && (
        <Notice tone="warning">요청이 많습니다. 잠시 후 다시 시도해 주세요.</Notice>
      )}
      {result === "error" && (
        <Notice tone="danger">보내지 못했습니다. 잠시 후 다시 시도해 주세요.</Notice>
      )}
    </form>
  )
}
