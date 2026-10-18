/**
 * 책임: [A] Vite/shadcn 스타일 최소 앱의 실행 확인 화면.
 * 구현할 기능: 프론트 단독 표시 및 Backend /health REST(Axios) 연결 진단.
 * 코드 경계: 체크리스트·로그인·LLM·RAG 실제 기능을 구현하지 않는다.
 * 완료 기준: npm run dev/build, API가 켜졌을 때 health 표시.
 */

import { Activity, ArrowUpRight, CheckCircle2, Code2, HeartPulse, Layers3 } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/shared/api/client"

type Health = { status: string; service: string }

export default function App() {
  const [health, setHealth] = useState<string>("아직 확인하지 않음")
  const [checking, setChecking] = useState(false)
  // /health 성공은 Backend 프로세스 응답만 뜻하며 DB·모델 연결 준비를 보장하지 않는다.
  async function checkBackend() {
    setChecking(true)
    try {
      const response = await api.get<Health>("/health")
      setHealth(`${response.data.service}: ${response.data.status}`)
    } catch {
      setHealth("연결 실패 — Backend 실행 상태 및 VITE_API_BASE_URL 확인")
    } finally {
      setChecking(false)
    }
  }
  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b bg-card/70">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-primary p-2 text-primary-foreground">
              <Layers3 className="size-5" />
            </div>
            <span className="text-lg font-bold">상속길잡이</span>
          </div>
          <span className="rounded-full border px-3 py-1 text-xs text-muted-foreground">
            실행 준비용 화면
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl space-y-8 px-6 py-12">
        <section className="max-w-2xl space-y-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            STARTER KIT · RUNTIME CHECK
          </p>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            개발 환경이 준비되었습니다.
          </h1>
          <p className="leading-7 text-muted-foreground">
            React 19 · Vite 8 · Tailwind CSS v4 · shadcn/ui 호환 구성입니다. 실제 상속 서비스 화면,
            로그인, AI 기능은 담당자 구현 전입니다.
          </p>
        </section>
        <div className="grid gap-5 md:grid-cols-2">
          <Card>
            <CardHeader>
              <div className="mb-2 flex size-10 items-center justify-center rounded-xl bg-secondary">
                <HeartPulse className="size-5" />
              </div>
              <CardTitle>Backend 연결 상태</CardTitle>
              <CardDescription>FastAPI /health 엔드포인트 테스트</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg bg-secondary p-3 text-sm" role="status">
                {health}
              </div>
              <Button onClick={checkBackend} disabled={checking}>
                <Activity className="size-4" />
                {checking ? "확인 중…" : "서버 상태 확인"}
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <div className="mb-2 flex size-10 items-center justify-center rounded-xl bg-secondary">
                <Code2 className="size-5" />
              </div>
              <CardTitle>개발자 다음 작업</CardTitle>
              <CardDescription>기능별 인터페이스부터 연결하세요</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p className="flex items-center gap-2">
                <CheckCircle2 className="size-4" />
                프론트 실행·빌드·타입 검사
              </p>
              <p className="flex items-center gap-2">
                <ArrowUpRight className="size-4" />
                인증·체크리스트·챗봇: 구현 전
              </p>
              <p className="flex items-center gap-2">
                <ArrowUpRight className="size-4" />
                LLM·RAG: CLI 계약 검증만 가능
              </p>
            </CardContent>
          </Card>
        </div>
        <p className="text-xs text-muted-foreground">
          이 화면은 진입점 테스트 전용입니다. 실제 서비스 UI 또는 승인된 ERD를 구현한 것이 아닙니다.
        </p>
      </main>
    </div>
  )
}
