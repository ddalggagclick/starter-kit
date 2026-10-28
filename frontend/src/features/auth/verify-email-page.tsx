/*
 * 담당: [A] | 책임: 인증 메일 링크 화면 /auth/verify#token=… (팀원 요청).
 * PRD: E5 / 태스크 5-5-1. 계약: A12 POST /api/auth/email/verify {verificationToken} (x-confirmed: true, 경로 제안).
 * 구현: #token을 읽고 주소에서 바로 지운 뒤 한 번만 요청한다. 성공이면 로그인 안내,
 *   만료·이미 사용·잘못된 링크는 사유를 구분하지 않고 같은 안내와 인증 메일 재전송 경로를 보인다.
 * 제한사항: 토큰을 로그·저장소에 남기지 않는다.
 */
import { useEffect, useState } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/ui/notice"
import { verifyEmailOnce } from "./auth-api"
import { AuthCard } from "./auth-form-field"
import { useLinkToken } from "./link-token"
import { ResendVerificationForm } from "./resend-verification-form"

type VerifyStatus = "verifying" | "success" | "failed"

export function VerifyEmailPage() {
  const token = useLinkToken()
  const [status, setStatus] = useState<VerifyStatus>(token ? "verifying" : "failed")

  useEffect(() => {
    if (!token) return
    let active = true
    verifyEmailOnce(token)
      .then(() => active && setStatus("success"))
      .catch(() => active && setStatus("failed"))
    return () => {
      active = false
    }
  }, [token])

  if (status === "verifying") {
    return (
      <AuthCard title="이메일 인증">
        <p role="status">인증하는 중…</p>
      </AuthCard>
    )
  }

  if (status === "success") {
    return (
      <AuthCard title="이메일 인증">
        <Notice tone="success">이메일 인증이 끝났습니다. 이제 로그인할 수 있습니다.</Notice>
        <Button asChild className="w-full">
          <Link to="/login">로그인하기</Link>
        </Button>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="이메일 인증">
      <Notice tone="danger">
        링크가 만료되었거나 이미 사용되었습니다. 인증 메일을 다시 받아 주세요.
      </Notice>
      <ResendVerificationForm />
    </AuthCard>
  )
}
