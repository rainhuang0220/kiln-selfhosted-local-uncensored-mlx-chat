import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Monitor, Moon, Sun } from "lucide-react";
import type { Health } from "../types/chat";
import type { ThemePref } from "../lib/theme";

export type RuntimeStatus = {
  title: string;
  detail: string | null;
  online: boolean;
};

export function runtimeStatus(health: Health | null | undefined): RuntimeStatus {
  const parked = Boolean(health?.chat?.state && health.chat.state !== "running");
  if (parked) {
    return { title: "视频生成中", detail: "聊天稍后恢复", online: false };
  }
  if (health?.provider?.reachable) {
    return { title: "模型在线", detail: null, online: true };
  }
  return { title: "模型离线", detail: "正在重连", online: false };
}

type FooterProps = {
  username: string | null;
  role: string | null;
  health: Health | null;
  theme: ThemePref;
  collapsed?: boolean;
  menuOpen?: boolean;
  onTheme: (theme: ThemePref) => void;
  onLogout: () => void;
};

export function SidebarFooter({
  username,
  role,
  health,
  theme,
  collapsed = false,
  menuOpen,
  onTheme,
  onLogout,
}: FooterProps) {
  const status = runtimeStatus(health);
  const [open, setOpen] = useState(Boolean(menuOpen));
  const controlled = menuOpen !== undefined;
  const shown = controlled ? menuOpen : open;

  return (
    <div className={collapsed ? "side-foot is-collapsed" : "side-foot"}>
      <div className="runtime-status" role="status" title={status.detail ? `${status.title} · ${status.detail}` : status.title}>
        <span className={status.online ? "dot on" : "dot"} />
        <span className="runtime-copy">
          <strong>{status.title}</strong>
          {status.detail ? <small>{status.detail}</small> : null}
        </span>
      </div>
      {username ? (
        <AccountMenu
          username={username}
          role={role}
          theme={theme}
          open={shown}
          onOpenChange={(next) => {
            if (!controlled) setOpen(next);
          }}
          onTheme={onTheme}
          onLogout={onLogout}
        />
      ) : null}
    </div>
  );
}

function AccountMenu({
  username,
  role,
  theme,
  open,
  onOpenChange,
  onTheme,
  onLogout,
}: {
  username: string;
  role: string | null;
  theme: ThemePref;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onTheme: (theme: ThemePref) => void;
  onLogout: () => void;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const initial = (username.trim()[0] || "?").toUpperCase();
  const roleLabel = role === "owner" ? "Owner" : role ? role[0].toUpperCase() + role.slice(1) : null;

  useLayoutEffect(() => {
    if (!open || !menuRef.current || !triggerRef.current) return;
    const menu = menuRef.current;
    const rect = triggerRef.current.getBoundingClientRect();
    const pad = 8;
    const w = Math.min(220, window.innerWidth - pad * 2);
    menu.style.width = `${w}px`;
    const h = menu.getBoundingClientRect().height || 240;
    let left = rect.left;
    if (left + w > window.innerWidth - pad) left = window.innerWidth - pad - w;
    if (left < pad) left = pad;
    menu.style.top = "auto";
    menu.style.bottom = `${Math.round(window.innerHeight - rect.top + 8)}px`;
    menu.style.left = `${Math.round(left)}px`;
    if (h > rect.top - pad) {
      menu.style.bottom = "auto";
      menu.style.top = `${Math.round(Math.max(pad, rect.bottom + 8))}px`;
    }
  }, [open, username, theme]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onOpenChange(false);
        triggerRef.current?.focus();
      }
    };
    const onPointer = (e: MouseEvent) => {
      const t = e.target as Node;
      if (menuRef.current?.contains(t) || triggerRef.current?.contains(t)) return;
      onOpenChange(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [open, onOpenChange]);

  const menu = open ? (
    <div
      ref={menuRef}
      id={menuId}
      className="account-menu"
      role="menu"
      aria-label="Account"
    >
      <div className="account-menu-head">
        <div className="account-menu-name">{username}</div>
        {roleLabel ? <div className="account-menu-role">{roleLabel}</div> : null}
      </div>
      <div className="account-menu-label" id={`${menuId}-appearance`}>
        Appearance
      </div>
      <div role="group" aria-labelledby={`${menuId}-appearance`}>
        {([
          ["system", "System", Monitor],
          ["light", "Light", Sun],
          ["dark", "Dark", Moon],
        ] as const).map(([value, label, Icon]) => (
          <button
            key={value}
            type="button"
            role="menuitemradio"
            aria-checked={theme === value}
            className={theme === value ? "account-item is-active" : "account-item"}
            onClick={() => onTheme(value)}
          >
            <Icon size={15} strokeWidth={1.75} />
            <span>{label}</span>
            {theme === value ? <span className="account-check" aria-hidden="true">✓</span> : null}
          </button>
        ))}
      </div>
      <div className="account-menu-rule" />
      <button type="button" role="menuitem" className="account-item is-logout" onClick={onLogout}>
        退出登录
      </button>
    </div>
  ) : null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="account-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        title={username}
        onClick={() => onOpenChange(!open)}
      >
        <span className="account-mark" aria-hidden="true">
          {initial}
        </span>
        <span className="account-name">{username}</span>
        <ChevronDown size={14} strokeWidth={1.75} aria-hidden="true" />
      </button>
      {menu ? <MenuPortal>{menu}</MenuPortal> : null}
    </>
  );
}

function MenuPortal({ children }: { children: ReactNode }) {
  if (typeof document === "undefined") return <>{children}</>;
  return createPortal(children, document.body);
}
