/** 책임: [A] shadcn/ui 공통 className 결합 도구.
 * 구현할 기능: clsx와 tailwind-merge로 Tailwind 클래스 충돌 정리.
 * 완료 기준: Button/Card에서 공통 사용 가능.
 */
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
