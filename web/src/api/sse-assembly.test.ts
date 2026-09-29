import { describe, expect, it } from "vitest";
import { acceptDelta, createAssembly } from "./sse-assembly";

describe("sse assembly", () => {
  it("appends an increasing sequence and keeps the request id", () => {
    const state = createAssembly();
    expect(acceptDelta(state, { request_id: "r1", seq: 1, content: "甲" })).toBe("accept");
    expect(acceptDelta(state, { request_id: "r1", seq: 2, content: "乙" })).toBe("accept");
    expect(state.text).toBe("甲乙");
    expect(state.requestId).toBe("r1");
  });

  it("does not append a duplicate sequence", () => {
    const state = createAssembly();
    acceptDelta(state, { request_id: "r1", seq: 1, content: "甲" });
    expect(acceptDelta(state, { request_id: "r1", seq: 1, content: "甲" })).toBe("duplicate");
    expect(state.text).toBe("甲");
  });

  it("does not pull a later frame forward across a gap", () => {
    const state = createAssembly();
    acceptDelta(state, { request_id: "r1", seq: 1, content: "甲" });
    expect(acceptDelta(state, { request_id: "r1", seq: 3, content: "丙" })).toBe("gap");
    expect(state.text).toBe("甲");
    expect(state.expectedSeq).toBe(2);
  });

  it("does not mix a second request into the same turn", () => {
    const state = createAssembly();
    acceptDelta(state, { request_id: "r1", seq: 1, content: "甲" });
    expect(acceptDelta(state, { request_id: "r2", seq: 2, content: "乙" })).toBe("foreign");
    expect(state.text).toBe("甲");
  });

  it("records malformed payloads without treating them as text", () => {
    const state = createAssembly();
    expect(acceptDelta(state, "{not-json")).toBe("malformed");
    expect(state.text).toBe("");
    expect(state.defects).toContain("malformed");
  });
});
