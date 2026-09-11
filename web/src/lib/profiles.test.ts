import { describe, expect, it } from "vitest";
import { PROFILE_PRESETS, isIncompleteTerminal, terminalCopy } from "./profiles";

describe("profiles", () => {
  it("interactive dialogue disables thinking", () => {
    expect(PROFILE_PRESETS.interactive_dialogue.enableThinking).toBe(false);
    expect(PROFILE_PRESETS.interactive_dialogue.maxTokens).toBeLessThanOrEqual(2048);
  });

  it("explains abnormal terminals", () => {
    expect(terminalCopy("interrupted_transport", null)).toBe("生成未正常完成");
    expect(isIncompleteTerminal("repetition_guard")).toBe(true);
    expect(isIncompleteTerminal("stop", "completed_stop")).toBe(false);
  });
});
