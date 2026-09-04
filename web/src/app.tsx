import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { LibraryBig, Menu, PanelLeftClose, PanelLeftOpen, Plus, Quote, Trash2 } from "lucide-react";
import { GenerateStudio } from "./generate";
import { Markdown } from "./components/Markdown";
import { ModelWorkbench } from "./components/ModelWorkbench";
import { groupConversations } from "./lib/groups";
import { applyTheme, readThemePref } from "./lib/theme";
import { formatTokens, formatTokensShort, relativeTime } from "./lib/time";
import { useChatStore } from "./stores/chat-store";

const STARTERS = [
  "Explain this machine's local Qwen setup in one paragraph.",
  "Write a Python function that streams an OpenAI-compatible SSE client.",
  "What should I remember about context windows vs RAM on a 24GB Mac?",
];

export function App() {
  const { id } = useParams();
  const navigate = useNavigate();
  const store = useChatStore();
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const wasStreaming = useRef(false);

  useEffect(() => {
    applyTheme(readThemePref());
    const onUnauth = () => {
      store.stop();
      useChatStore.setState({ authRequired: true, authOk: false });
    };
    window.addEventListener("kiln:unauthorized", onUnauth);
    void store.loadHealth();
    void store.loadConversations();
    void store.loadModels();
    const t = window.setInterval(() => void store.loadHealth(), 10000);
    const onVis = () => {
      if (document.visibilityState === "visible") void store.loadHealth();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.clearInterval(t);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("kiln:unauthorized", onUnauth);
    };
  }, []);

  useEffect(() => {
    if (id && id !== store.activeId) void store.openConversation(id);
  }, [id]);

  useEffect(() => {
    if (store.activeId && !id) {
      navigate(`/c/${store.activeId}`, { replace: true });
    }
  }, [store.activeId, id, navigate]);

  useEffect(() => {
    if (store.streaming && !wasStreaming.current) stickToBottom.current = true;
    wasStreaming.current = store.streaming;
    const el = scroller.current;
    if (!el || !stickToBottom.current) return;
    el.scrollTop = el.scrollHeight;
  }, [store.messages, store.streaming]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "n") {
        e.preventDefault();
        store.stop();
        navigate("/");
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "i") {
        e.preventDefault();
        store.toggleInspector();
      }
      if (e.key === "Escape" && store.streaming) store.stop();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [store.streaming]);

  const title = useMemo(() => {
    const found = store.conversations.find((c) => c.id === store.activeId);
    return found?.title || "New conversation";
  }, [store.conversations, store.activeId]);

  const [gateUser, setGateUser] = useState("");
  const [gatePass, setGatePass] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [view, setView] = useState<"chat" | "generate">("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => window.localStorage.getItem("kiln.sidebar") === "collapsed",
  );
  const [modelWorkbenchOpen, setModelWorkbenchOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 900px)").matches,
  );
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 900px)");
    const onChange = () => {
      setIsMobile(mq.matches);
      if (mq.matches) {
        useChatStore.setState({ inspectorOpen: false });
        setSidebarOpen(false);
      }
    };
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && sidebarOpen) setSidebarOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sidebarOpen]);

  useEffect(() => {
    document.body.classList.toggle("nav-locked", sidebarOpen);
    return () => document.body.classList.remove("nav-locked");
  }, [sidebarOpen]);

  const closeSidebar = () => setSidebarOpen(false);
  const toggleSidebar = () => {
    setSidebarCollapsed((collapsed) => {
      const next = !collapsed;
      window.localStorage.setItem("kiln.sidebar", next ? "collapsed" : "open");
      return next;
    });
  };
  if (store.authRequired && !store.authOk) {
    return (
      <div className="auth-gate">
        <form
          className="auth-card"
          onSubmit={(e) => {
            e.preventDefault();
            if (store.authSetup) {
              void store.register(gateUser, gatePass);
            } else {
              void store.login(gateUser, gatePass);
            }
          }}
        >
          <p className="auth-kicker">Kiln · public kiln</p>
          <h1>{store.authSetup ? "创建账号" : "登录"}</h1>
          <p>
            {store.authSetup
              ? "还没有用户。用户名 3–32 位（小写字母数字下划线），密码至少 10 位。"
              : "用户名和密码登录。会话存在本机 Cookie，密码只存 Argon2 哈希。"}
          </p>
          <input
            type="text"
            autoFocus
            autoComplete="username"
            placeholder="用户名"
            value={gateUser}
            onChange={(e) => setGateUser(e.target.value)}
          />
          <input
            type="password"
            autoComplete={store.authSetup ? "new-password" : "current-password"}
            placeholder="密码"
            value={gatePass}
            onChange={(e) => setGatePass(e.target.value)}
          />
          {store.authError ? <p className="auth-error">{store.authError}</p> : null}
          <button className="btn primary" type="submit" disabled={!gateUser.trim() || !gatePass}>
            {store.authSetup ? "创建并进入" : "进入"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div
      className={[
        "shell",
        store.inspectorOpen && view === "chat" ? "" : "inspector-closed",
        sidebarOpen ? "sidebar-open" : "",
        sidebarCollapsed ? "sidebar-collapsed" : "",
        view === "generate" ? "gen-view" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <button
        type="button"
        className="nav-scrim mobile-only"
        aria-label="Close conversations"
        onClick={closeSidebar}
      />
      <aside className="sidebar" aria-label="Conversations">
        <div className="brand">
          <div className="brand-lockup"><h1>Kiln</h1>
          <span>local fire</span>
          </div>
          <button
            type="button"
            className="icon-btn desktop-sidebar-toggle"
            aria-label={sidebarCollapsed ? "Expand conversations" : "Collapse conversations"}
            onClick={toggleSidebar}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
          <button
            type="button"
            className="icon-btn mobile-only sidebar-close"
            aria-label="Close conversations"
            onClick={closeSidebar}
          >
            <span className="icon-x" />
          </button>
        </div>
        <div className="mode-tabs" role="tablist" aria-label="Kiln mode">
          <button type="button" role="tab" aria-selected={view === "chat"} className={view === "chat" ? "on" : ""} onClick={() => setView("chat")}>Chat</button>
          <button type="button" role="tab" aria-selected={view === "generate"} className={view === "generate" ? "on" : ""} onClick={() => setView("generate")}>Generate</button>
        </div>
        <div className="side-actions">
          <button
            className="btn primary full"
            onClick={() => {
              store.stop();
              void store.openConversation(null);
              navigate("/");
              setView("chat");
              closeSidebar();
            }}
          >
            <Plus size={15} /> New chat
          </button>
          <button className="btn ghost full model-library-launch" type="button" onClick={() => setModelWorkbenchOpen(true)}>
            <LibraryBig size={15} /> Model library
          </button>
          <input
            className="search"
            placeholder="Search"
            value={store.searchQuery}
            onChange={(e) => store.setSearch(e.target.value)}
            aria-label="Search conversations"
          />
        </div>
        <div className="conv-list">
          {store.conversations.length === 0 ? (
            <div className="conv-item">
              <strong>No conversations on this machine.</strong>
            </div>
          ) : (
            groupConversations(store.conversations).map((g) => (
              <div key={g.label}>
                <div className="group-label">{g.label}</div>
                {g.items.map((c) => (
                  <ConversationRow
                    key={c.id}
                    active={c.id === store.activeId}
                    title={c.title || "Untitled"}
                    meta={`${relativeTime(c.updated_at)} · ${formatTokens(c.total_tokens)} tok`}
                    onOpen={() => {
                      navigate(`/c/${c.id}`);
                      closeSidebar();
                    }}
                    onRename={(title) => void store.rename(c.id, title)}
                    onRemove={() => {
                      if (window.confirm(`Delete “${c.title || "Untitled"}”?`)) void store.remove(c.id);
                    }}
                  />
                ))}
              </div>
            ))
          )}
        </div>
        <div className="side-foot">
          <span className="pill">
            <span className={store.health?.provider.reachable ? "dot on" : "dot"} />
            {store.health?.chat?.state && store.health.chat.state !== "running"
              ? "视频生成中，聊天稍后恢复"
              : store.health?.provider.reachable
                ? "模型在线"
                : "模型离线，正在重连"}
          </span>
          <div className="side-foot-right">
            {store.username ? <span className="who">{store.username}</span> : null}
            {store.authRequired ? (
              <button type="button" className="btn ghost" onClick={() => void store.logout()}>
                退出
              </button>
            ) : null}
            <ThemeSwitch />
          </div>
        </div>
      </aside>

      <main className="chat">
        {view === "generate" ? (
          <>
            <header className="chat-head">
              <button type="button" className="icon-btn mobile-only" aria-label="Open conversations" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(true)}>
                <Menu size={18} />
              </button>
              <h2>Generate</h2>
            </header>
            {store.health?.chat?.state && store.health.chat.state !== "running" ? (
              <div className="banner" role="status">
                {store.health.chat.message || "Chat is temporarily unavailable while local video generation is using system memory. It will resume automatically when the job finishes."}
              </div>
            ) : null}
            <GenerateStudio />
          </>
        ) : (
          <>
            {store.health?.chat?.state && store.health.chat.state !== "running" ? (
              <div className="banner" role="status">
                {store.health.chat.message || "Chat is temporarily unavailable while local video generation is using system memory. It will resume automatically when the job finishes."}
              </div>
            ) : null}
        <header className="chat-head">
          <button
            type="button"
            className="icon-btn mobile-only"
            aria-label="Open conversations"
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen(true)}
          >
            <Menu size={18} />
          </button>
          <h2>{title}</h2>
          <div className="head-actions">
            {store.activeId ? (
              <button
                className="btn ghost danger"
                onClick={async () => {
                  if (!store.activeId) return;
                  await store.remove(store.activeId);
                  navigate("/");
                }}
              >
                <Trash2 size={15} /> Delete
              </button>
            ) : null}
            <button className="btn ghost desktop-only" type="button" onClick={() => setModelWorkbenchOpen(true)}>
              Models
            </button>
            <button
              className="btn ghost desktop-only"
              aria-expanded={store.inspectorOpen}
              aria-controls="inspector"
              onClick={() => store.toggleInspector()}
            >
              Context
            </button>
            <ContextChip />
          </div>
        </header>
        <div
          className="transcript"
          ref={scroller}
          role="log"
          aria-live="polite"
          onScroll={(e) => {
            const el = e.currentTarget;
            const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
            stickToBottom.current = gap < 96;
          }}
        >
          {store.messages.length === 0 ? (
            <div className="empty">
              <h3>Strike a conversation.</h3>
              <p>
                Kiln talks to the local Qwen on this Mac. Turns accumulate in SQLite;
                occupancy sits in the corner.
              </p>
              <div className="starters">
                {STARTERS.map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      store.setDraft(s);
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            store.messages.map((m) => (
              <article key={m.id} className={`turn ${m.role}`}>
                <div className="role">{m.role}</div>
                <div className="body">
                  {m.role === "assistant" && m.reasoning ? (
                    <details className="think">
                      <summary>Thought</summary>
                      <pre>{m.reasoning}</pre>
                    </details>
                  ) : null}
                  {m.role === "assistant" ? (
                    <Markdown text={m.content} streaming={m.status === "streaming"} />
                  ) : (
                    m.content
                  )}
                  {m.role === "assistant" && m.usage ? (
                    <div className="meta-row">
                      <span>↑ {formatTokens(m.usage.input)}</span>
                      <span>↓ {formatTokens(m.usage.output)}</span>
                      <span>Σ {formatTokens(m.usage.total)}</span>
                      {m.usage.tokensPerSecond ? (
                        <span>{m.usage.tokensPerSecond.toFixed(1)} tok/s</span>
                      ) : null}
                      {m.finish_reason === "length" ? (
                        <span style={{ color: "var(--copper-2)" }}>hit max tokens</span>
                      ) : null}
                    </div>
                  ) : null}
                  {m.role === "assistant" && m.status !== "streaming" ? (
                    <div className="msg-actions">
                      <button
                        className="btn ghost"
                        onClick={() => void navigator.clipboard.writeText(m.content)}
                      >
                        Copy
                      </button>
                      {store.messages[store.messages.length - 1]?.id === m.id ? (
                        <>
                          <button className="btn ghost" onClick={() => void store.send("regenerate")}>
                            Regenerate
                          </button>
                          {m.status === "error" || m.status === "interrupted" ? (
                            <button className="btn ghost" onClick={() => void store.send("regenerate")}>
                              Retry
                            </button>
                          ) : null}
                        </>
                      ) : null}
                      <button
                        className="btn ghost"
                        onClick={() => store.setDraft(`> ${m.content.replace(/\n/g, "\n> ")}\n\n`)}
                      >
                        <Quote size={14} /> Quote
                      </button>
                      {m.id && !m.id.startsWith("local-") ? (
                        <button
                          className="btn ghost danger"
                          onClick={() => {
                            if (window.confirm("Delete this response?")) void store.removeMessage(m.id);
                          }}
                        >
                          <Trash2 size={14} /> Delete
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                  {m.role === "user" && m.id && !m.id.startsWith("local-") ? (
                    <div className="msg-actions user-actions">
                      <button
                        className="btn ghost"
                        onClick={() => store.setDraft(`> ${m.content.replace(/\n/g, "\n> ")}\n\n`)}
                      >
                        <Quote size={14} /> Quote
                      </button>
                      <button
                        className="btn ghost danger"
                        onClick={() => {
                          if (window.confirm("Delete this turn and its response?")) void store.removeMessage(m.id);
                        }}
                      >
                        <Trash2 size={14} /> Delete turn
                      </button>
                    </div>
                  ) : null}
                  {m.error ? <div className="banner">{m.error}</div> : null}
                </div>
              </article>
            ))
          )}
        </div>
        {!store.health?.provider.reachable ? (
          <div className="banner" role="status">
            模型暂时离线。Mac 上的 mlx 由 LaunchAgent 常驻，通常会在一两分钟内自动拉起，请稍后再发。
          </div>
        ) : null}
        {store.error ? (
          <div className="banner" role="alert">
            {store.error === "mlx unreachable: All connection attempts failed"
              ? "暂时连不上本机模型（8081）。服务会自动重启，加载权重可能要一两分钟。"
              : store.error}
          </div>
        ) : null}
        <div
          className={dragOver ? "composer-wrap drop-target" : "composer-wrap"}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files?.length) void store.attachFiles(e.dataTransfer.files);
          }}
        >
          <div className="composer">
            <textarea
              value={store.draft}
              placeholder={
                store.health?.provider.reachable
                  ? isMobile
                    ? "写给窑火。点 Send 发送。"
                    : "Write to the kiln. Enter to send, Shift+Enter for a newline. Drop text files here."
                  : "模型离线，正在自动重连。加载完成后即可发送。"
              }
              rows={3}
              onChange={(e) => store.setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                if (e.key === "Enter" && !e.shiftKey) {
                  if (window.matchMedia("(max-width: 900px)").matches) return;
                  e.preventDefault();
                  void store.send();
                }
              }}
            />
            <div className="composer-bar">
              <div className="toggles">
                <label>
                  <input
                    type="checkbox"
                    checked={store.params.enableThinking}
                    onChange={(e) => store.setParams({ enableThinking: e.target.checked })}
                  />
                  thinking
                </label>
                <select
                  value={store.params.reasoningEffort}
                  onChange={(e) =>
                    store.setParams({
                      reasoningEffort: e.target.value as "low" | "medium" | "xhigh",
                    })
                  }
                >
                  <option value="low">low</option>
                  <option value="medium">mid</option>
                  <option value="xhigh">max</option>
                </select>
                <label>
                  max
                  <input
                    type="number"
                    min={64}
                    max={store.health?.max_tokens_cap || 32768}
                    step={64}
                    value={store.params.maxTokens}
                    onChange={(e) => store.setParams({ maxTokens: Number(e.target.value) })}
                    style={{ width: 80, background: "transparent", border: 0, color: "inherit" }}
                  />
                </label>
                <label className="file-btn">
                  file
                  <input
                    ref={fileRef}
                    type="file"
                    multiple
                    hidden
                    onChange={(e) => {
                      if (e.target.files?.length) void store.attachFiles(e.target.files);
                      e.target.value = "";
                    }}
                  />
                </label>
              </div>
              {store.streaming ? (
                <button className="btn" onClick={() => store.stop()}>
                  Stop
                </button>
              ) : (
                <button
                  className="btn primary"
                  disabled={!store.draft.trim()}
                  onClick={() => void store.send()}
                >
                  Send
                </button>
              )}
            </div>
          </div>
        </div>
          </>
        )}
      </main>

      <aside className="inspector" id="inspector" aria-label="Context inspector">
        <div className="inspector-head">
          <h3>Context</h3>
          <span style={{ color: "var(--muted)", fontSize: 12 }}>what the model saw</span>
        </div>
        <Inspector />
      </aside>
      <ModelWorkbench open={modelWorkbenchOpen} onClose={() => setModelWorkbenchOpen(false)} />
    </div>
  );
}

function ContextChip() {
  const snapshot = useChatStore((s) => s.snapshot);
  const health = useChatStore((s) => s.health);
  const occ = snapshot?.occupancy;
  const prompt = occ?.prompt_tokens ?? 0;
  const win = occ?.effective_window_tokens ?? health?.practical_prompt_budget ?? 0;
  const pct = win ? Math.min(100, Math.round((prompt / win) * 100)) : 0;
  const packed = Boolean(occ?.document_pack?.applied);
  const truncated = Boolean(snapshot?.truncation.applied);
  const online = Boolean(health?.provider.reachable);
  const warn = pct > 85 || packed || truncated;
  return (
    <div
      className={warn ? "ctx-chip warn" : "ctx-chip"}
      role="status"
      title={
        online
          ? `Context ${formatTokens(prompt)} / ${formatTokens(win)}`
          : "Model offline"
      }
    >
      <span className={online ? "dot on" : "dot"} />
      <span className={warn ? "meter warn" : "meter"}>
        <span style={{ width: `${pct}%` }} />
      </span>
      <b>
        {formatTokensShort(prompt)}/{formatTokensShort(win)}
      </b>
    </div>
  );
}

function ThemeSwitch() {
  const [pref, setPref] = useState(readThemePref());
  return (
    <div className="theme-switch" role="group" aria-label="Theme">
      {(["light", "dark", "system"] as const).map((t) => (
        <button
          key={t}
          className={pref === t ? "btn primary" : "btn ghost"}
          onClick={() => {
            setPref(t);
            applyTheme(t);
          }}
        >
          {t === "light" ? "Light" : t === "dark" ? "Dark" : "System"}
        </button>
      ))}
    </div>
  );
}

function ConversationRow({
  active,
  title,
  meta,
  onOpen,
  onRename,
  onRemove,
}: {
  active: boolean;
  title: string;
  meta: string;
  onOpen: () => void;
  onRename: (title: string) => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  return (
    <div className={active ? "conv-item active" : "conv-item"}>
      {editing ? (
        <input
          className="search"
          value={draft}
          autoFocus
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => {
            setEditing(false);
            if (draft.trim() && draft.trim() !== title) onRename(draft.trim());
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          }}
        />
      ) : (
        <>
          <button type="button" className="conv-open" onClick={onOpen} onDoubleClick={() => setEditing(true)}>
            <strong>{title}</strong>
            <em>{meta}</em>
          </button>
          <button type="button" className="conv-delete" onClick={onRemove} aria-label={`Delete ${title}`}>
            <Trash2 size={14} />
          </button>
        </>
      )}
    </div>
  );
}

function Inspector() {
  const snapshot = useChatStore((s) => s.snapshot);
  const health = useChatStore((s) => s.health);
  const messages = useChatStore((s) => s.messages);
  const last = [...messages].reverse().find((m) => m.role === "assistant");
  if (!snapshot) {
    return (
      <div className="inspector-body">
        <div className="card">
          <h4>Waiting</h4>
          <p style={{ margin: 0, color: "var(--muted)", fontSize: 13 }}>
            Send a turn to capture the exact payload posted to mlx_lm.server.
          </p>
        </div>
        <div className="card">
          <h4>Budget</h4>
          <div className="kv">
            <span>practical window</span>
            <b>{formatTokens(health?.practical_prompt_budget)}</b>
            <span>model max</span>
            <b>{formatTokens(health?.context_window)}</b>
          </div>
        </div>
      </div>
    );
  }
  const occ = snapshot.occupancy;
  const pct = Math.min(100, Math.round((occ.ratio || 0) * 100));
  return (
    <div className="inspector-body">
      <div className="card">
        <h4>Occupancy</h4>
        <div className={occ.ratio > 0.85 ? "meter warn" : "meter"}>
          <span style={{ width: `${pct}%` }} />
        </div>
        <div className="kv" style={{ marginTop: 8 }}>
          <span>prompt</span>
          <b>
            {formatTokens(occ.prompt_tokens)} / {formatTokens(occ.effective_window_tokens)}
          </b>
          <span>model max</span>
          <b>{formatTokens(occ.model_max_tokens)}</b>
          <span>output budget</span>
          <b>{formatTokens(occ.completion_budget)}</b>
        </div>
        {snapshot.truncation.applied ? (
          <p style={{ color: "var(--copper-2)", fontSize: 12, margin: "8px 0 0" }}>
            Dropped {snapshot.truncation.dropped_message_ids.length} earlier turns.
          </p>
        ) : null}
        {occ.document_pack?.applied ? (
          <p style={{ color: "var(--copper-2)", fontSize: 12, margin: "8px 0 0" }}>
            Packed document {formatTokens(occ.document_pack.original_tokens)} →{" "}
            {formatTokens(occ.document_pack.kept_tokens)} (
            {occ.document_pack.chunks_kept}/{occ.document_pack.chunks_total} chunks).
          </p>
        ) : null}
      </div>
      <div className="card">
        <h4>Tokens</h4>
        <div className="kv">
          <span>input</span>
          <b>{formatTokens(last?.usage?.input ?? occ.prompt_tokens)}</b>
          <span>output</span>
          <b>{formatTokens(last?.usage?.output)}</b>
          <span>total</span>
          <b>{formatTokens(last?.usage?.total)}</b>
          <span>cached</span>
          <b>{formatTokens(last?.usage?.cached)}</b>
          <span>tok/s</span>
          <b>
            {last?.usage?.tokensPerSecond != null
              ? last.usage.tokensPerSecond.toFixed(1)
              : "—"}
          </b>
        </div>
      </div>
      <div className="card">
        <h4>Params</h4>
        <div className="kv">
          {Object.entries(snapshot.params || {}).map(([k, v]) =>
            typeof v === "object" ? null : (
              <span key={k} style={{ display: "contents" }}>
                <span>{k}</span>
                <b>{String(v)}</b>
              </span>
            ),
          )}
        </div>
      </div>
      {snapshot.history_summary ? (
        <div className="card">
          <h4>Compressed history</h4>
          <div className="sys">{snapshot.history_summary}</div>
        </div>
      ) : null}
      <div className="card">
        <h4>System prompt</h4>
        <div className="sys">{snapshot.effective_system_prompt || "—"}</div>
      </div>
      <div className="card">
        <h4>Sent messages</h4>
        <div className="sent">
          {snapshot.sent_messages.map((m, i) => (
            <div className="sent-item" key={i}>
              <b>
                {i + 1}. {m.role}
              </b>
              {m.content}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
