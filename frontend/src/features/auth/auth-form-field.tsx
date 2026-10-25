/*
 * 담당: [A] | 책임: 인증 화면(가입·재설정·탈퇴)의 공통 입력칸과 화면 틀.
 * 구현: 라벨·오류 문구를 입력칸에 연결해(aria-describedby) 화면낭독기가 오류를 읽게 한다.
 */
import type { ReactNode } from "react"
import { useId } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export function AuthCard({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
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
      <input
        id={id}
        type={type}
        autoComplete={autoComplete}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={message ? messageId : undefined}
        className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
      />
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
