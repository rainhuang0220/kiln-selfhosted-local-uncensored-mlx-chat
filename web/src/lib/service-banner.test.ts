import { describe, expect, it } from "vitest";
import { serviceBanner } from "./service-banner";
import type { Health } from "../types/chat";

function health(partial: Partial<Health>): Health {
  return {
    status: "ok",
    provider: { name: "mlx", reachable: true, base_url: "" },
    model: "qwen3.5-9b",
    context_window: 262144,
    practical_prompt_budget: 32768,
    default_max_tokens: 1536,
    enable_thinking: false,
    ...partial,
  };
}

describe("serviceBanner", () => {
  it("stays quiet when the gateway is available", () => {
    expect(serviceBanner(health({ gateway: { state: "AVAILABLE" } }))).toBeNull();
  });

  it("does not call a video pause a crash", () => {
    expect(
      serviceBanner(
        health({
          provider: { name: "mlx", reachable: false, base_url: "" },
          gateway: { state: "VIDEO_SUSPENDED", suspension_reason: "video" },
        }),
      ),
    ).toBe("视频任务正在使用内存，文本模型被主动暂停。");
  });

  it("keeps a dead port distinct from a dead API", () => {
    expect(serviceBanner(health({ gateway: { state: "OFFLINE" } }))).toBe("连不上本机模型端口。");
    expect(serviceBanner(health({ status: "down", gateway: { state: "API_UNREACHABLE" } }))).toBe(
      "Kiln 接口没有响应。这不能说明模型进程已经退出。",
    );
  });

  it("says the port is up when only inference is degraded", () => {
    expect(
      serviceBanner(
        health({
          gateway: { state: "DEGRADED" },
        }),
      ),
    ).toBe("模型端口还在，但最近的生成没有正常完成。");
  });
});
