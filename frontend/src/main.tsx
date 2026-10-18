/** 책임: [A] React 진입점.
 * 구현할 기능: root 노드에 앱을 마운트하고 Tailwind 테마 불러오기.
 * 완료 기준: npm run dev 실행 시 기본 화면 표시.
 */
import React from "react"
import ReactDOM from "react-dom/client"
import App from "./app"
import "./index.css"

const root = document.getElementById("root")
if (!root) throw new Error("Missing root element")

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
