import { describe, expect, it } from "vitest";
import {
  PROFILE_HELP,
  PROFILE_LABELS,
  PROFILE_PRESETS,
  PROFILE_PRIMARY,
  isIncompleteTerminal,
  terminalCopy,
} from "./profiles";

describe("profiles", () => {
  it("default immersive uses a 6144 token budget", () => {
    expect(PROFILE_PRESETS.immersive.profile).toBe("immersive");
    expect(PROFILE_PRESETS.immersive.maxTokens).toBe(6144);
    expect(PROFILE_PRESETS.immersive.presencePenalty).toBe(0.25);
    expect(PROFILE_PRESETS.immersive.presenceContextSize).toBe(1024);
    expect(PROFILE_PRESETS.immersive.frequencyPenalty).toBe(0);
    expect(PROFILE_PRESETS.immersive.repetitionPenalty).toBe(1.0);
    expect(PROFILE_PRESETS.long_form.frequencyPenalty).toBe(0);
  });

  it("primary dropdown is only immersive and short dialogue", () => {
    expect(PROFILE_PRIMARY).toEqual(["immersive", "interactive_dialogue"]);
    expect(PROFILE_LABELS.immersive).toBe("沉浸对话");
    expect(PROFILE_LABELS.interactive_dialogue).toBe("短对话");
    expect(PROFILE_PRIMARY).not.toContain("balanced");
    expect(PROFILE_HELP.immersive).toMatch(/钉过的事实/);
    expect(PROFILE_HELP.interactive_dialogue).toMatch(/不会自动续写/);
  });

  it("interactive dialogue uses 3072 tokens", () => {
    expect(PROFILE_PRESETS.interactive_dialogue.enableThinking).toBe(false);
    expect(PROFILE_PRESETS.interactive_dialogue.maxTokens).toBe(3072);
    expect(PROFILE_PRESETS.fast.maxTokens).toBe(3072);
  });

  it("keeps legacy presets off the primary list", () => {
    expect(PROFILE_PRESETS.balanced.presenceContextSize).toBe(256);
    expect(PROFILE_PRESETS.long_form.maxTokens).toBe(6144);
    expect(PROFILE_PRIMARY).not.toContain("reasoning");
    expect(PROFILE_PRIMARY).not.toContain("long_form");
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
