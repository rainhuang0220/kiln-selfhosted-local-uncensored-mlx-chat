import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AuthGate } from "./AuthGate";

const ready = {
  authChecked: true,
  authRequired: true,
  authOk: false,
  authReady: true,
  authSetup: false,
  authError: null as string | null,
  lockedUser: null as string | null,
  login: vi.fn(async () => false),
  register: vi.fn(async () => false),
};

describe("AuthGate", () => {
  it("associates visible labels with username and password fields", () => {
    const html = renderToStaticMarkup(<AuthGate {...ready} />);
    expect(html).toContain('for="auth-username"');
    expect(html).toContain('id="auth-username"');
    expect(html).toContain('for="auth-password"');
    expect(html).toContain('id="auth-password"');
    expect(html).toMatch(/<label[^>]*for="auth-username"[^>]*>用户名<\/label>/);
    expect(html).toMatch(/<label[^>]*for="auth-password"[^>]*>密码<\/label>/);
  });

  it("keeps password-manager autocomplete and remember-me off by default", () => {
    const html = renderToStaticMarkup(<AuthGate {...ready} />);
    expect(html).toMatch(/autoComplete="username"|autocomplete="username"/);
    expect(html).toMatch(/autoComplete="current-password"|autocomplete="current-password"/);
    expect(html).toContain('id="auth-remember"');
    expect(html).toContain("在此设备保持登录 7 天");
    expect(html).not.toMatch(/id="auth-remember"[^>]*checked/);
    expect(html).toContain('type="button"');
    expect(html).toContain("显示密码");
    expect(html).toContain('type="password"');
  });

  it("exposes opaque auth errors to assistive tech without naming which field failed", () => {
    const html = renderToStaticMarkup(<AuthGate {...ready} authError="用户名或密码不对" />);
    expect(html).toContain('role="alert"');
    expect(html).toContain("用户名或密码不对");
    expect(html).not.toContain("用户不存在");
    expect(html).not.toContain("密码错误");
  });

  it("shows the locked account as a labeled current-user field", () => {
    const html = renderToStaticMarkup(<AuthGate {...ready} lockedUser="rain" />);
    expect(html).toContain("当前账号");
    expect(html).toContain("rain");
    expect(html).toMatch(/readonly/i);
    expect(html).toContain("已锁定");
  });

  it("does not offer public registration when the owner is not ready", () => {
    const html = renderToStaticMarkup(<AuthGate {...ready} authReady={false} />);
    expect(html).toContain("create-owner");
    expect(html).not.toContain("创建并进入");
    expect(html).toMatch(/disabled/);
  });
});
