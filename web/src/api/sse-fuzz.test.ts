import { describe, expect, it } from "vitest";
import { createAssembly, observeFrame } from "./sse-assembly";
import { readSse } from "./stream";

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function textFor(rng: () => number): string {
  const alphabet = "甲乙丙丁窑火ok-代码_id\n“”";
  const n = 8 + Math.floor(rng() * 40);
  let out = "";
  for (let i = 0; i < n; i += 1) out += alphabet[Math.floor(rng() * alphabet.length)];
  return out;
}

function partsOf(text: string, rng: () => number): string[] {
  const parts: string[] = [];
  let i = 0;
  while (i < text.length) {
    const n = 1 + Math.floor(rng() * 5);
    parts.push(text.slice(i, i + n));
    i += n;
  }
  return parts;
}

function sse(events: { event: string; data: unknown }[]): Uint8Array {
  const raw = events
    .map((ev) => `event: ${ev.event}\ndata: ${JSON.stringify(ev.data)}\n\n`)
    .join("");
  return new TextEncoder().encode(raw);
}

function chunked(bytes: Uint8Array, rng: () => number): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let i = 0;
      while (i < bytes.length) {
        const n = 1 + Math.floor(rng() * 17);
        controller.enqueue(bytes.subarray(i, Math.min(bytes.length, i + n)));
        i += n;
      }
      controller.close();
    },
  });
  return new Response(stream, { headers: { "Content-Type": "text/event-stream" } });
}

async function assemble(events: { event: string; data: unknown }[], rng: () => number) {
  const state = createAssembly();
  for await (const ev of readSse(chunked(sse(events), rng))) {
    if (ev.event === "delta" || ev.event === "done" || ev.event === "meta") {
      observeFrame(state, ev.data, ev.event === "delta");
    }
  }
  return state;
}

describe("sse fuzz", () => {
  it("reassembles 1000 randomly cut streams without inventing or reordering text", async () => {
    const rng = mulberry32(20260925);
    for (let n = 0; n < 1000; n += 1) {
      const text = textFor(rng);
      const parts = partsOf(text, rng);
      const requestId = `r${n}`;
      const events = [
        { event: "meta", data: { request_id: requestId, seq: 1, conversation_id: "c" } },
        ...parts.map((content, i) => ({
          event: "delta",
          data: { request_id: requestId, seq: i + 2, content },
        })),
        {
          event: "done",
          data: { request_id: requestId, seq: parts.length + 2, finish_reason: "stop" },
        },
      ];
      const state = await assemble(events, rng);
      expect(state.text, `case ${n}`).toBe(text);
      expect(state.defects, `case ${n}`).toEqual([]);
      expect(state.requestId).toBe(requestId);
    }
  });

  it("flags duplicate, gap, foreign, and malformed frames instead of repairing them", async () => {
    const rng = mulberry32(7);
    for (let n = 0; n < 1000; n += 1) {
      const kind = n % 4;
      const text = textFor(rng);
      const parts = partsOf(text, rng);
      const requestId = `r${n}`;
      const events: { event: string; data: unknown }[] = [
        { event: "meta", data: { request_id: requestId, seq: 1 } },
      ];
      if (kind === 0) {
        events.push({ event: "delta", data: { request_id: requestId, seq: 2, content: parts[0] } });
        events.push({ event: "delta", data: { request_id: requestId, seq: 2, content: parts[0] } });
        const state = await assemble(events, rng);
        expect(state.text).toBe(parts[0]);
        expect(state.defects).toContain("duplicate");
      } else if (kind === 1) {
        events.push({ event: "delta", data: { request_id: requestId, seq: 2, content: parts[0] } });
        events.push({ event: "delta", data: { request_id: requestId, seq: 4, content: "后" } });
        const state = await assemble(events, rng);
        expect(state.text).toBe(parts[0]);
        expect(state.text.includes("后")).toBe(parts[0].includes("后"));
        expect(state.defects).toContain("gap");
        expect(state.expectedSeq).toBe(3);
      } else if (kind === 2) {
        events.push({ event: "delta", data: { request_id: requestId, seq: 2, content: parts[0] } });
        events.push({ event: "delta", data: { request_id: "other", seq: 3, content: "串" } });
        const state = await assemble(events, rng);
        expect(state.text).toBe(parts[0]);
        expect(state.defects).toContain("foreign");
      } else {
        const state = createAssembly();
        const decision = observeFrame(state, "{not-json", true);
        expect(decision).toBe("malformed");
        expect(state.text).toBe("");
      }
    }
  });
});
