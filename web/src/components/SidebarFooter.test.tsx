import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { runtimeStatus, SidebarFooter } from "./SidebarFooter";

const healthOnline = {
  provider: { reachable: true },
  chat: { state: "running" },
} as never;

const healthOffline = {
  provider: { reachable: false },
  chat: { state: "running" },
} as never;

const healthParked = {
  provider: { reachable: false },
  chat: { state: "parked" },
} as never;

describe("runtimeStatus", () => {
  it("uses a short online label", () => {
    expect(runtimeStatus(healthOnline)).toEqual({
      title: "模型在线",
      detail: null,
      online: true,
    });
  });

  it("keeps offline detail off the title row", () => {
    expect(runtimeStatus(healthOffline)).toEqual({
      title: "模型离线",
      detail: "正在重连",
      online: false,
    });
  });

  it("treats parked chat as a video occupancy status", () => {
    expect(runtimeStatus(healthParked)).toEqual({
      title: "视频生成中",
      detail: "聊天稍后恢复",
      online: false,
    });
  });

  it("does not call a live port healthy when inference is degraded", () => {
    expect(
      runtimeStatus({
        provider: { reachable: true },
        chat: { state: "running" },
        gateway: { state: "DEGRADED" },
      } as never),
    ).toEqual({
      title: "生成异常",
      detail: "端口还在，最近的生成没有完成",
      online: false,
    });
  });

  it("keeps an expired verification distinct from a live model", () => {
    expect(
      runtimeStatus({
        provider: { reachable: true },
        gateway: { state: "AVAILABLE", inference_capability: "UNVERIFIED", last_verified_at: 1 },
      } as never),
    ).toEqual({
      title: "端口在线",
      detail: "近期生成尚未验证",
      online: true,
    });
  });

  it("names a failed generator without calling the queue busy", () => {
    expect(
      runtimeStatus({
        provider: { reachable: true },
        gateway: { state: "DEGRADED", inference_capability: "FAILED" },
      } as never),
    ).toEqual({
      title: "生成失败",
      detail: "端口还在，生成没有成功",
      online: false,
    });
  });

  it("does not claim a completed generation before one has succeeded", () => {
    expect(
      runtimeStatus({
        provider: { reachable: true },
        chat: { state: "running" },
        gateway: { state: "AVAILABLE", last_verified_at: null },
      } as never),
    ).toEqual({
      title: "端口在线",
      detail: "近期生成尚未验证",
      online: true,
    });
  });

  it("says the model is online after a verified generation", () => {
    expect(
      runtimeStatus({
        provider: { reachable: true },
        gateway: { state: "AVAILABLE", last_verified_at: 1 },
      } as never),
    ).toEqual({
      title: "模型在线",
      detail: null,
      online: true,
    });
  });

  it("does not blame the model when the API itself is down", () => {
    expect(
      runtimeStatus({
        provider: { reachable: false },
        gateway: { state: "API_UNREACHABLE" },
      } as never),
    ).toEqual({
      title: "接口无响应",
      detail: "不能据此判断模型进程",
      online: false,
    });
  });
});

describe("SidebarFooter", () => {
  it("does not show lock, logout, or theme as persistent toolbar buttons", () => {
    const html = renderToStaticMarkup(
      <SidebarFooter
        username="rain"
        role="owner"
        health={healthOnline}
        theme="system"
        onTheme={vi.fn()}
        onLogout={vi.fn()}
      />,
    );
    expect(html).toContain("模型在线");
    expect(html).toContain("rain");
    expect(html).not.toContain("锁定");
    expect(html).not.toContain(">退出<");
    expect(html).not.toContain("Light");
    expect(html).not.toContain("Dark");
    expect(html).not.toContain("System");
    expect(html).toContain('aria-haspopup="menu"');
    expect(html).toContain('aria-expanded="false"');
  });

  it("puts theme and logout in the open account menu, still without lock", () => {
    const html = renderToStaticMarkup(
      <SidebarFooter
        username="rain"
        role="owner"
        health={healthOnline}
        theme="system"
        menuOpen
        onTheme={vi.fn()}
        onLogout={vi.fn()}
      />,
    );
    expect(html).toContain("Owner");
    expect(html).toContain("System");
    expect(html).toContain("Light");
    expect(html).toContain("Dark");
    expect(html).toContain("退出登录");
    expect(html).not.toContain("锁定");
    expect(html).toContain('aria-checked="true"');
  });
});
