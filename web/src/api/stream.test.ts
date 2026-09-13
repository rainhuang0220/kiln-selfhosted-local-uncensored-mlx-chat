import { readSse } from "./stream";
import { describe, expect, it } from "vitest";

function responseFrom(text: string): Response {
  return new Response(text, { headers: { "Content-Type": "text/event-stream" } });
}

async function collect(res: Response) {
  const out = [];
  for await (const ev of readSse(res)) out.push(ev);
  return out;
}

describe("readSse", () => {
  it("does not treat HTTP EOF as success", async () => {
    const events = await collect(
      responseFrom('event: delta\ndata: {"content":"partial"}\n\n'),
    );
    expect(events.some((ev) => ev.event === "transport_eof")).toBe(true);
    expect(events.some((ev) => ev.event === "done")).toBe(false);
  });

  it("keeps app-level done distinct from wire DONE", async () => {
    const events = await collect(
      responseFrom(
        'event: done\ndata: {"finish_reason":"stop","incomplete":false}\n\ndata: [DONE]\n\n',
      ),
    );
    expect(events.map((ev) => ev.event)).toContain("done");
    expect(events.some((ev) => ev.event === "transport_eof")).toBe(false);
  });

  it("yields ping without closing the reader", async () => {
    const events = await collect(
      responseFrom(
        'event: ping\ndata: {"ok":true}\n\nevent: done\ndata: {"finish_reason":"stop"}\n\n',
      ),
    );
    expect(events[0]).toEqual({ event: "ping", data: { ok: true } });
    expect(events.some((ev) => ev.event === "done")).toBe(true);
  });
});
