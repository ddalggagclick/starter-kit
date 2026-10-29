/*
 * 담당: [A] | 책임: 인증 화면(가입·재설정·탈퇴)의 공통 입력칸과 화면 틀.
 * 구현: 라벨·오류 문구를 입력칸에 연결해(aria-describedby) 화면낭독기가 오류를 읽게 한다.
 *   #227 새 시안(https://claude.ai/artifact/NgrnTfYvGvuGj5PYWnJcfu): 로그인·회원가입·비밀번호 재설정·회원 탈퇴는 지금 화면 위
 *   모달로도 열린다. 모달 안이면 AuthCard는 카드 틀 없이 로고 + 가운데 제목으로 그리고, AuthLink는 페이지 이동 대신
 *   다른 인증 모달로 바꾸거나(예: 로그인 → 회원가입) 모달을 닫는다. 주소로 열면(메일 링크 등) 전처럼 페이지다.
 */
import { Eye, EyeOff } from "lucide-react"
import type { ComponentProps, ReactNode } from "react"
import { useId, useState } from "react"
import { Link } from "react-router"
import logoImage from "@/assets/logo.png"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { type OverlayName, useInOverlay, useOverlayStore } from "@/shared/state/overlay-store"

export function AuthCard({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  const inOverlay = useInOverlay()
  if (inOverlay) {
    return (
      <div className="space-y-4">
        <div className="flex flex-col items-center gap-2 px-8 text-center">
          <img src={logoImage} alt="" className="mx-auto mb-1 size-10 rounded-lg" />
          <h2 className="text-xl font-semibold leading-none">{title}</h2>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
        {children}
      </div>
    )
  }
  return (
    <div className="mx-auto max-w-md">
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent className="space-y-4">{children}</CardContent>
      </Card>
    </div>
  )
}

// 인증 화면 사이 이동 링크. 모달 안이면 overlay로 바꾸거나("close"면 닫기) 하고, 페이지면 to로 이동한다.
export function AuthLink({
  to,
  state,
  overlay,
  className = "text-sm underline underline-offset-4",
  children,
}: {
  to: string
  state?: unknown
  overlay: OverlayName | "close"
  className?: string
  children: ReactNode
}) {
  const inOverlay = useInOverlay()
  const open = useOverlayStore((s) => s.open)
  const close = useOverlayStore((s) => s.close)
  if (inOverlay) {
    return (
      <button
        type="button"
        className={className}
        onClick={() => (overlay === "close" ? close() : open(overlay))}
      >
        {children}
      </button>
    )
  }
  return (
    <Link to={to} state={state} className={className}>
      {children}
    </Link>
  )
}

// 시안: 비밀번호 칸 오른쪽 [비밀번호 표시] 버튼. 누르면 글자를 보이고(aria-pressed), 다시 누르면 숨긴다.
export function PasswordInput({ className, ...props }: Omit<ComponentProps<"input">, "type">) {
  const [shown, setShown] = useState(false)
  return (
    <div className="relative">
      <input {...props} type={shown ? "text" : "password"} className={`${className ?? ""} pr-11`} />
      <button
        type="button"
        aria-label={shown ? "비밀번호 숨기기" : "비밀번호 표시"}
        aria-pressed={shown}
        onClick={() => setShown((value) => !value)}
        className="absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-md text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        {shown ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
      </button>
    </div>
  )
}

export const AUTH_INPUT_CLASS =
  "h-11 w-full rounded-md border border-input bg-transparent px-3 text-base shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-invalid:border-danger-foreground"

export function AuthField({
  label,
  type,
  value,
  onChange,
  error,
  autoComplete,
  hint,
}: {
  label: string
  type: "email" | "password"
  value: string
  onChange: (value: string) => void
  error?: string | null
  autoComplete?: string
  hint?: string
}) {
  const id = useId()
  const messageId = useId()
  const message = error ?? hint
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {type === "password" ? (
        <PasswordInput
          id={id}
          autoComplete={autoComplete}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={message ? messageId : undefined}
          className={AUTH_INPUT_CLASS}
        />
      ) : (
        <input
          id={id}
          type={type}
          autoComplete={autoComplete}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={message ? messageId : undefined}
          className={AUTH_INPUT_CLASS}
        />
      )}
      {message && (
        <p
          id={messageId}
          className={error ? "text-sm text-danger-foreground" : "text-xs text-muted-foreground"}
        >
          {message}
        </p>
      )}
    </div>
  )
}
