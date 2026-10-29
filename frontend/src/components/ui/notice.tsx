/** 책임: [A] 여러 화면이 쓰는 안내 띠(공통 위험 경고·Handoff 결과·Mock 표시 등).
 * 구현할 기능: info/warning/danger/success 색 구분과 role 지정.
 * 완료 기준: 경고·오류는 role="alert", 일반 안내는 role="status"로 읽힌다.
 */
import { TriangleAlert } from "lucide-react"
import type * as React from "react"
import { cn } from "@/lib/utils"

const TONES = {
  info: "bg-info text-info-foreground",
  warning: "bg-warning text-warning-foreground",
  danger: "bg-danger text-danger-foreground",
  success: "bg-success text-success-foreground",
} as const

export function Notice({
  tone = "info",
  className,
  ...props
}: React.ComponentProps<"div"> & { tone?: keyof typeof TONES }) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("rounded-lg px-4 py-3 text-sm leading-6", TONES[tone], className)}
      {...props}
    />
  )
}

// #227 새 시안: 공통 위험 경고를 글자 한 줄짜리 작은 노란 표시로 보인다. 읽힘(role="status")은 Notice와 같다.
export function WarningPill({ className, children }: React.ComponentProps<"div">) {
  return (
    <Notice
      tone="warning"
      className={cn(
        "inline-flex w-fit items-center gap-1.5 rounded-md border border-warning-foreground/20 px-3 py-1.5 text-sm leading-normal",
        className,
      )}
    >
      <TriangleAlert className="size-4 shrink-0" aria-hidden />
      <span>{children}</span>
    </Notice>
  )
}
