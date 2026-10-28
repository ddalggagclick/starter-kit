/*
 * 담당: [A] | 책임: POST 응답 본문(text/event-stream)을 SSE 이벤트 단위로 읽는다.
 * PRD: E3 / 태스크 3-5-1, 3-4-3. API: A08 SseEvents (status / result / error 3종, 협의 4).
 * 구현: ReadableStream을 TextDecoder로 이어 붙이고 빈 줄(\n\n)마다 event·data를 나눈다. data 여러 줄은 \n으로 합친다.
 * 제한사항: EventSource(GET 전용)를 쓰지 않는다. JSON 해석·화면 반영은 use-chat-stream이 한다.
 */
export type RawSseEvent = { event: string; data: string }

const parseBlock = (block: string): RawSseEvent | null => {
  let event = "message"
  const data: string[] = []
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue
    const colon = line.indexOf(":")
    const field = colon === -1 ? line : line.slice(0, colon)
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "")
    if (field === "event") event = value
    else if (field === "data") data.push(value)
  }
  return data.length > 0 ? { event, data: data.join("\n") } : null
}

export async function* readSseEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<RawSseEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, "\n")
      let boundary = buffer.indexOf("\n\n")
      while (boundary !== -1) {
        const parsed = parseBlock(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        if (parsed) yield parsed
        boundary = buffer.indexOf("\n\n")
      }
    }
    const tail = parseBlock((buffer + decoder.decode()).trim())
    if (tail) yield tail
  } finally {
    reader.releaseLock()
  }
}
