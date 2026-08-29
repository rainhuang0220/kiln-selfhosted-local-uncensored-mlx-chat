export interface SseEvent {
  event: string;
  data: unknown;
}

function parseBlock(raw: string): SseEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  const data = dataLines.join("\n");
  if (!data) return null;
  if (data === "[DONE]") return { event: "done_wire", data: "[DONE]" };
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data };
  }
}

export async function* readSse(
  response: Response,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  if (!response.body) throw new Error("no response body");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  const flush = (chunk: string): SseEvent[] => {
    buf += chunk.replace(/\r\n/g, "\n");
    const out: SseEvent[] = [];
    while (true) {
      const idx = buf.indexOf("\n\n");
      if (idx < 0) break;
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const parsed = parseBlock(raw);
      if (parsed) out.push(parsed);
    }
    return out;
  };

  try {
    while (true) {
      if (signal?.aborted) {
        throw new DOMException("Aborted", "AbortError");
      }
      const { done, value } = await reader.read();
      if (done) {
        const rest = flush(decoder.decode());
        for (const ev of rest) {
          if (ev.event === "done_wire") return;
          yield ev;
        }
        if (buf.trim()) {
          const parsed = parseBlock(buf);
          if (parsed && parsed.event !== "done_wire") yield parsed;
        }
        return;
      }
      for (const ev of flush(decoder.decode(value, { stream: true }))) {
        if (ev.event === "done_wire") return;
        yield ev;
      }
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      /* ignore */
    }
  }
}
