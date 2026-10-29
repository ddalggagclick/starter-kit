/** 책임: [A] shadcn/ui 형태의 최소 Button 컴포넌트.
 * 구현할 기능: 기본/outline/secondary 변형과 asChild Slot 호환.
 * 완료 기준: App에서 Button 렌더 및 클릭이 작동.
 * #227 새 시안(NgrnTfYvGvuGj5PYWnJcfu)의 버튼 모양: 모바일 글자 16px·PC 14px, 그림자, 3px 초점 테두리, 높이 40/36/44px.
 *   시안 지시 2: 768px 미만에서는 누르는 영역을 최소 44×44px로 한다(max-md:min-h-11 min-w-11).
 */

import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import type * as React from "react"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-base font-medium outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 max-md:min-h-11 max-md:min-w-11 md:text-sm",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-xs hover:bg-primary/90",
        outline: "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/85",
        // 테두리·바탕 없는 버튼
        ghost: "hover:bg-accent hover:text-accent-foreground",
        // 되돌릴 수 없는 동작(삭제·철회) 확인 버튼(시안: 빨간 바탕)
        destructive: "bg-danger-foreground text-white shadow-xs hover:opacity-90",
      },
      size: { default: "h-10 px-4", sm: "h-9 rounded-md px-3", lg: "h-11 rounded-md px-6" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
)
function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button"
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
