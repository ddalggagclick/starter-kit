/**
 * 책임: [A] shadcn/ui Vite 기본 플러그인 및 @ alias.
 * 구현할 기능: React 플러그인, Tailwind v4 빌드, shadcn CLI 컴포넌트 alias.
 * 완료 기준: npm run dev/build 실행, @/components resolve.
 */
import path from "node:path"
import { fileURLToPath } from "node:url"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
})
