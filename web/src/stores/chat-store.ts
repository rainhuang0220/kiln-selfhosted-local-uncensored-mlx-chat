import { create } from "zustand";
import { apiFetch } from "../api/http";
import { readSse } from "../api/stream";
import { heuristicTitle } from "../lib/markdown";
import { applyTheme } from "../lib/theme";
import type {
  ContextSnapshot,
  ConversationSummary,
  GenerationParams,
  Health,
  HubModel,
  LocalModel,
  Message,
  ModelDownloadJob,
  TokenUsage,
} from "../types/chat";

const DEFAULT_PARAMS: GenerationParams = {
  temperature: 1.0,
  topP: 0.95,
  topK: 20,
  maxTokens: 8192,
  enableThinking: true,
  reasoningEffort: "medium",
};

interface ChatState {
  health: Health | null;
  conversations: ConversationSummary[];
  activeId: string | null;
  messages: Message[];
  draft: string;
  params: GenerationParams;
  inspectorOpen: boolean;
  snapshot: ContextSnapshot | null;
  streaming: boolean;
  error: string | null;
  controller: AbortController | null;
  authRequired: boolean;
  authOk: boolean;
  authError: string | null;
  authSetup: boolean;
  authSignup: boolean;
  username: string | null;
  localModels: LocalModel[];
  activeModelId: string | null;
  modelCatalog: HubModel[];
  modelJobs: ModelDownloadJob[];
  loadHealth: () => Promise<void>;
  loadModels: () => Promise<void>;
  searchModelCatalog: (query: string, mlxOnly?: boolean) => Promise<void>;
  queueModelDownload: (repoId: string, activate?: boolean) => Promise<boolean>;
  activateModel: (modelId: string) => Promise<boolean>;
  loadModelJobs: () => Promise<void>;
  login: (username: string, password: string) => Promise<boolean>;
  register: (username: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  searchQuery: string;
  theme: "light" | "dark" | "system";
  loadConversations: (q?: string) => Promise<void>;
  openConversation: (id: string | null) => Promise<void>;
  setDraft: (v: string) => void;
  attachFiles: (files: FileList | File[]) => Promise<void>;
  setParams: (p: Partial<GenerationParams>) => void;
  toggleInspector: () => void;
  send: (mode?: "regenerate") => Promise<void>;
  stop: () => void;
  remove: (id: string) => Promise<void>;
  removeMessage: (messageId: string) => Promise<void>;
  rename: (id: string, title: string) => Promise<void>;
  setSearch: (q: string) => void;
  setTheme: (t: "light" | "dark" | "system") => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  health: null,
  conversations: [],
  activeId: null,
  messages: [],
  draft: "",
  params: DEFAULT_PARAMS,
  inspectorOpen: true,
  searchQuery: "",
  theme: "light",
  snapshot: null,
  streaming: false,
  error: null,
  controller: null,
  authRequired: false,
  authOk: true,
  authError: null,
  authSetup: false,
  authSignup: false,
  username: null,
  localModels: [],
  activeModelId: null,
  modelCatalog: [],
  modelJobs: [],

  loadModels: async () => {
    const response = await apiFetch("/models/local");
    if (!response.ok) return;
    const body = await response.json();
    set({ localModels: body.data || [], activeModelId: body.active_id || null });
  },

  searchModelCatalog: async (query, mlxOnly = false) => {
    const params = new URLSearchParams({ q: query, mlx_only: String(mlxOnly) });
    const response = await apiFetch(`/models/catalog?${params.toString()}`);
    if (!response.ok) {
      set({ error: "无法读取 Hugging Face 模型目录" });
      return;
    }
    const body = await response.json();
    set({ modelCatalog: body.data || [] });
  },

  loadModelJobs: async () => {
    const response = await apiFetch("/models/download");
    if (!response.ok) return;
    const body = await response.json();
    set({ modelJobs: body.data || [] });
  },

  queueModelDownload: async (repoId, activate = false) => {
    const response = await apiFetch("/models/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_id: repoId, activate }),
    });
    if (!response.ok) {
      set({ error: "模型下载任务未能创建" });
      return false;
    }
    const job = await response.json();
    set((state) => ({ modelJobs: [job, ...state.modelJobs] }));
    return true;
  },

  activateModel: async (modelId) => {
    const response = await apiFetch(`/models/${encodeURIComponent(modelId)}/activate`, {
      method: "POST",
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      set({ error: body?.error?.message || "模型切换未能启动" });
      return false;
    }
    await Promise.all([get().loadModels(), get().loadHealth()]);
    return true;
  },

  login: async (username: string, password: string) => {
    const r = await apiFetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!r.ok) {
      set({ authOk: false, authRequired: true, authError: "用户名或密码不对" });
      return false;
    }
    const body = await r.json();
    set({
      authOk: true,
      authRequired: true,
      authError: null,
      username: body.username || username,
    });
    await get().loadHealth();
    await get().loadConversations();
    return true;
  },

  register: async (username: string, password: string) => {
    const r = await apiFetch("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => null);
      set({
        authOk: false,
        authRequired: true,
        authError: err?.error?.message || "注册失败",
      });
      return false;
    }
    const body = await r.json();
    set({
      authOk: true,
      authRequired: true,
      authError: null,
      authSetup: false,
      username: body.username || username,
    });
    await get().loadHealth();
    await get().loadConversations();
    return true;
  },

  logout: async () => {
    await apiFetch("/auth/logout", { method: "POST" });
    get().stop();
    set({
      authOk: false,
      authRequired: true,
      username: null,
      conversations: [],
      activeId: null,
      messages: [],
      snapshot: null,
    });
  },

  loadHealth: async () => {
    try {
      const auth = await apiFetch("/auth/status");
      if (auth.ok) {
        const s = await auth.json();
        set({
          authRequired: Boolean(s.required),
          authOk: Boolean(s.ok),
          authSetup: Boolean(s.setup),
          authSignup: Boolean(s.signup),
          username: s.username || null,
        });
        if (s.required && !s.ok) return;
      }
      const r = await apiFetch("/health");
      if (!r.ok) throw new Error("health failed");
      const health = await r.json();
      const params = get().params;
      const nextParams =
        params.maxTokens <= 2048 && health.default_max_tokens
          ? { ...params, maxTokens: health.default_max_tokens }
          : params;
      set({ health, params: nextParams });
    } catch {
      set({
        health: {
          status: "down",
          provider: { name: "mlx", reachable: false, base_url: "" },
          model: "qwen3.5-9b-hauhau-aggressive-mxfp4",
          context_window: 262144,
          practical_prompt_budget: 32768,
          default_max_tokens: 8192,
          max_tokens_cap: 32768,
          enable_thinking: true,
        },
      });
    }
  },

  setSearch: (q) => {
    set({ searchQuery: q });
    void get().loadConversations(q);
  },

  setTheme: (t) => {
    set({ theme: t });
    applyTheme(t);
  },

  loadConversations: async (q?: string) => {
    const query = q ?? get().searchQuery;
    const r = await apiFetch("/conversation" + (query ? `?q=${encodeURIComponent(query)}` : ""));
    if (!r.ok) return;
    const body = await r.json();
    set({ conversations: body.data || [] });
  },

  openConversation: async (id) => {
    get().stop();
    if (!id) {
      set({ activeId: null, messages: [], snapshot: null, error: null });
      return;
    }
    set({ activeId: id, error: null });
    const r = await apiFetch(`/conversation/${id}`);
    if (!r.ok) {
      if (get().activeId === id) {
        set({ activeId: null, messages: [], error: "conversation not found" });
      }
      return;
    }
    const body = await r.json();
    const messages: Message[] = (body.messages || [])
      .filter((m: Message) => m.role !== "system")
      .map((m: Message) => {
        const rawStatus = String(m.status || "complete");
        const status: Message["status"] =
          rawStatus === "cancelled"
            ? "interrupted"
            : ((rawStatus as Message["status"]) || "complete");
        return {
          ...m,
          status,
          usage:
            m.prompt_tokens != null
              ? {
                  input: m.prompt_tokens || 0,
                  output: m.completion_tokens || 0,
                  total: m.total_tokens || 0,
                }
              : undefined,
        };
      });
    let snapshot: ContextSnapshot | null = null;
    const ctx = await apiFetch(`/conversation/${id}/context`);
    if (ctx.ok) {
      const c = await ctx.json();
      if (c && c.payload) {
        const health = get().health;
        const win = health?.practical_prompt_budget || 32768;
        const prompt = c.tokens?.prompt_actual || c.tokens?.prompt_estimated || 0;
        const payload = c.payload;
        snapshot = {
          request_id: c.id,
          conversation_id: id,
          model: body.model,
          params: {
            temperature: payload.temperature,
            top_p: payload.top_p,
            top_k: payload.top_k,
            max_tokens: payload.max_tokens,
            enable_thinking: payload.enable_thinking,
            reasoning_effort: payload.reasoning_effort,
          },
          effective_system_prompt: c.effective_system_prompt || "",
          sent_messages: payload.messages || [],
          occupancy: {
            effective_window_tokens: win,
            model_max_tokens: health?.context_window || 262144,
            prompt_tokens: prompt,
            completion_budget: payload.max_tokens || 8192,
            reserved_output_tokens: payload.max_tokens || 8192,
            ratio: win ? prompt / win : 0,
          },
          truncation: {
            applied: Boolean(c.truncated),
            policy: c.truncated ? "drop_oldest" : "none",
            dropped_message_ids: c.dropped_message_ids || [],
          },
        };
      }
    }
    if (get().activeId !== id) return;
    set({ messages, snapshot, error: null });
  },

  setDraft: (v) => set({ draft: v }),

  attachFiles: async (files) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    const chunks: string[] = [];
    for (const file of list) {
      if (file.size > 12 * 1024 * 1024) {
        set({ error: `${file.name} exceeds 12MB` });
        continue;
      }
      const text = await file.text();
      if (text.includes("\u0000")) {
        set({ error: `${file.name} looks binary; use text, markdown, or code` });
        continue;
      }
      chunks.push(`\n\n# File: ${file.name}\n\n${text}`);
    }
    if (!chunks.length) return;
    const draft = get().draft;
    set({ draft: (draft ? draft.replace(/\s*$/, "") : "") + chunks.join(""), error: null });
  },
  setParams: (p) => set({ params: { ...get().params, ...p } }),
  toggleInspector: () => set({ inspectorOpen: !get().inspectorOpen }),

  stop: () => {
    const c = get().controller;
    if (c) c.abort();
  },

  remove: async (id) => {
    await apiFetch(`/conversation/${id}`, { method: "DELETE" });
    if (get().activeId === id) {
      set({ activeId: null, messages: [], snapshot: null });
    }
    await get().loadConversations();
  },

  removeMessage: async (messageId) => {
    const conversationId = get().activeId;
    if (!conversationId) return;
    const response = await apiFetch(
      `/conversation/${encodeURIComponent(conversationId)}/message/${encodeURIComponent(messageId)}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      set({ error: "删除消息失败" });
      return;
    }
    await Promise.all([get().openConversation(conversationId), get().loadConversations()]);
  },

  rename: async (id, title) => {
    await apiFetch(`/conversation/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    await get().loadConversations();
  },

  send: async (mode) => {
    const regen = mode === "regenerate";
    const lastUser = [...get().messages].reverse().find((m) => m.role === "user");
    const text = regen ? (lastUser?.content || "").trim() : get().draft.trim();
    if (!text || get().streaming) return;
    if (regen && !get().activeId) return;
    const params = get().params;
    const controller = new AbortController();
    const userMsg: Message = {
      id: lastUser?.id || `local-user-${Date.now()}`,
      role: "user",
      content: text,
      status: "complete",
    };
    const assistantMsg: Message = {
      id: `local-asst-${Date.now()}`,
      role: "assistant",
      content: "",
      reasoning: "",
      status: "streaming",
    };
    const prior = regen
      ? get().messages.filter((m, i, arr) => !(m.role === "assistant" && i === arr.length - 1))
      : get().messages;
    set({
      streaming: true,
      error: null,
      controller,
      messages: regen ? [...prior, assistantMsg] : [...prior, userMsg, assistantMsg],
    });

    const started = performance.now();
    let asstId = assistantMsg.id;
    let userId = userMsg.id;
    let accepted = false;
    try {
      const res = await apiFetch("/chat", {
        method: "POST",
        signal: controller.signal,
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          message: regen ? "" : text,
          conversation_id: get().activeId,
          regenerate: regen,
          stream: true,
          temperature: params.temperature,
          top_p: params.topP,
          top_k: params.topK,
          max_tokens: params.maxTokens,
          enable_thinking: params.enableThinking,
          reasoning_effort: params.reasoningEffort,
        }),
      });
      if (!res.ok) {
        if (res.status === 503) {
          const body = await res.json().catch(() => null);
          throw new Error(
            body?.message ||
              body?.error?.message ||
              "Chat is temporarily unavailable while local video generation is using system memory.",
          );
        }
        const err = await res.text();
        throw new Error(err || `HTTP ${res.status}`);
      }
      let content = "";
      let reasoning = "";
      let usage: TokenUsage | undefined;
      for await (const ev of readSse(res, controller.signal)) {
        if (ev.event === "meta") {
          const data = ev.data as {
            conversation_id: string;
            message_id: string;
            user_message_id: string;
            created: boolean;
          };
          accepted = true;
          userId = data.user_message_id;
          asstId = data.message_id;
          set((s) => ({
            activeId: data.conversation_id,
            draft: "",
            messages: s.messages.map((m) => {
              if (m.id === userMsg.id) return { ...m, id: userId };
              if (m.id === assistantMsg.id) return { ...m, id: asstId };
              return m;
            }),
          }));
          if (data.created) {
            const summary: ConversationSummary = {
              id: data.conversation_id,
              title: heuristicTitle(text),
              model: get().health?.model || "qwen3.5-9b-hauhau-aggressive-mxfp4",
              created_at: Date.now(),
              updated_at: Date.now(),
              message_count: 2,
              last_message_preview: text,
              total_tokens: 0,
            };
            set((s) => ({ conversations: [summary, ...s.conversations] }));
            /* App.tsx syncs /c/:id from activeId */
          }
        } else if (ev.event === "snapshot") {
          const snap = ev.data as ContextSnapshot;
          set({ snapshot: snap });
        } else if (ev.event === "delta") {
          const data = ev.data as { content?: string; reasoning?: string };
          if (data.reasoning) reasoning += data.reasoning;
          if (data.content) content += data.content;
          set((s) => ({
            messages: s.messages.map((m) =>
              m.id === asstId
                ? {
                    ...m,
                    content,
                    reasoning,
                    usage: {
                      input: s.snapshot?.occupancy.prompt_tokens || 0,
                      output: usage?.output || 0,
                      total: usage?.total || 0,
                      cached: usage?.cached,
                    },
                  }
                : m,
            ),
          }));
        } else if (ev.event === "usage") {
          usage = ev.data as TokenUsage;
          const elapsed = (performance.now() - started) / 1000;
          if (elapsed > 0 && usage.output) usage.tokensPerSecond = usage.output / elapsed;
          set((s) => ({
            messages: s.messages.map((m) =>
              m.id === asstId ? { ...m, usage } : m,
            ),
          }));
        } else if (ev.event === "error") {
          const data = ev.data as { error?: { message?: string; code?: string } };
          if (data.error?.code === "CHAT_MODEL_PARKED") {
            throw new Error(
              data.error.message ||
                "Chat is temporarily unavailable while local video generation is using system memory.",
            );
          }
          throw new Error(data.error?.message || "generation failed");
        } else if (ev.event === "done") {
          const data = ev.data as {
            finish_reason: string;
            usage?: {
              prompt_tokens: number;
              completion_tokens: number;
              total_tokens: number;
            };
            message?: { content?: string; reasoning_content?: string };
          };
          const elapsed = (performance.now() - started) / 1000;
          const u: TokenUsage = usage || {
            input: data.usage?.prompt_tokens || 0,
            output: data.usage?.completion_tokens || 0,
            total: data.usage?.total_tokens || 0,
          };
          if (elapsed > 0 && u.output) u.tokensPerSecond = u.output / elapsed;
          set((s) => ({
            messages: s.messages.map((m) =>
              m.id === asstId
                ? {
                    ...m,
                    content: data.message?.content ?? content,
                    reasoning: data.message?.reasoning_content ?? reasoning,
                    status: "complete",
                    usage: u,
                    prompt_tokens: u.input,
                    completion_tokens: u.output,
                    total_tokens: u.total,
                    finish_reason: data.finish_reason,
                  }
                : m,
            ),
          }));
        }
      }
      await get().loadConversations();
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === asstId ? { ...m, status: "interrupted" } : m,
          ),
        }));
      } else {
        set((s) => ({
          error: (err as Error).message,
          draft: accepted ? s.draft : text,
          messages: accepted
            ? s.messages.map((m) =>
                m.id === asstId
                  ? { ...m, status: "error", error: (err as Error).message }
                  : m,
              )
            : s.messages.filter((m) => m.id !== userId && m.id !== asstId),
        }));
      }
    } finally {
      if (get().controller === controller) {
        set({ streaming: false, controller: null });
      }
    }
  },
}));
