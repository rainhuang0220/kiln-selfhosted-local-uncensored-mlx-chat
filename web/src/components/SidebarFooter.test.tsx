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
