export type AssemblyDecision = "accept" | "duplicate" | "gap" | "foreign" | "malformed";

export interface SseAssembly {
  requestId: string | null;
  expectedSeq: number;
  text: string;
  defects: AssemblyDecision[];
}

interface Frame {
  request_id?: unknown;
  seq?: unknown;
  content?: unknown;
  reasoning?: unknown;
}

export function createAssembly(seed = ""): SseAssembly {
  return { requestId: null, expectedSeq: 1, text: seed, defects: [] };
}

export function observeFrame(state: SseAssembly, data: unknown, applyText: boolean): AssemblyDecision {
  if (data == null || typeof data !== "object") {
    state.defects.push("malformed");
    return "malformed";
  }
  const row = data as Frame;
  const seq = row.seq;
  const requestId = typeof row.request_id === "string" ? row.request_id : null;
  if (typeof seq !== "number") {
    if (applyText && typeof row.content === "string") state.text += row.content;
    return "accept";
  }
  if (requestId && state.requestId && requestId !== state.requestId) {
    state.defects.push("foreign");
    return "foreign";
  }
  if (requestId) state.requestId = requestId;
  if (seq < state.expectedSeq) {
    state.defects.push("duplicate");
    return "duplicate";
  }
  if (seq !== state.expectedSeq) {
    state.defects.push("gap");
    return "gap";
  }
  if (applyText && typeof row.content === "string") state.text += row.content;
  state.expectedSeq = seq + 1;
  return "accept";
}

export function acceptDelta(state: SseAssembly, data: unknown): AssemblyDecision {
  return observeFrame(state, data, true);
}
