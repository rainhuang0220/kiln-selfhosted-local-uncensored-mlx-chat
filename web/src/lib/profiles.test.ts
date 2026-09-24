import { describe, expect, it } from "vitest";
import { PROFILE_PRESETS, isIncompleteTerminal, terminalCopy } from "./profiles";

describe("profiles", () => {
  it("balanced sampling context matches the backend profile", () => {
    expect(PROFILE_PRESETS.balanced.presenceContextSize).toBe(256);
    expect(PROFILE_PRESETS.balanced.frequencyContextSize).toBe(256);
    expect(PROFILE_PRESETS.balanced.repetitionContextSize).toBe(128);
  });

  it("interactive dialogue disables thinking", () => {
    expect(PROFILE_PRESETS.interactive_dialogue.enableThinking).toBe(false);
    expect(PROFILE_PRESETS.interactive_dialogue.maxTokens).toBeLessThanOrEqual(2048);
  });

  it("explains abnormal terminals", () => {
    expect(terminalCopy("interrupted_transport", null)).toBe("生成未正常完成");
    expect(terminalCopy("length", null)).toBe("已达到输出上限");
    expect(terminalCopy("stop", "completed_stop")).toBeNull();
    expect(isIncompleteTerminal("repetition_guard")).toBe(true);
    expect(isIncompleteTerminal("stop", "completed_stop")).toBe(false);
    expect(isIncompleteTerminal("length", "completed_length")).toBe(false);
    expect(terminalCopy("stop", "completed_with_transport_error")).toBe("传输有损坏，这段回复可能缺字");
    expect(isIncompleteTerminal("stop", "completed_with_transport_error")).toBe(true);
  });
});
