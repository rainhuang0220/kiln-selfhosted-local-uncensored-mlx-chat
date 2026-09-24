import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../api/http";
import { isIncompleteTerminal, terminalCopy } from "../lib/profiles";
import { useChatStore } from "./chat-store";

vi.mock("../api/http", () => ({
  apiFetch: vi.fn(),
}));

const mocked = vi.mocked(apiFetch);

function sse(body: string): Response {
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function chatThenConversations(chatBody: string) {
  mocked.mockImplementation(async (url: string) => {
    if (url === "/chat") return sse(chatBody);
    if (String(url).startsWith("/conversation")) return json({ data: [] });
    throw new Error(`unmocked ${url}`);
  });
}

describe("auth privacy", () => {
  beforeEach(() => {
    mocked.mockReset();
    useChatStore.setState({
      authRequired: true,
      authOk: false,
      authChecked: true,
      username: null,
      conversations: [{ id: "c1" } as never],
      messages: [{ id: "m1" } as never],
      draft: "secret",
    });
  });

  it("keeps lock as a session-revoke primitive", async () => {
    useChatStore.setState({ username: "rain", authOk: true, draft: "secret" });
    mocked.mockResolvedValue(json({ ok: true, locked: true }));
    await useChatStore.getState().lock();
    expect(mocked.mock.calls[0][0]).toBe("/auth/lock");
    expect(mocked.mock.calls[0][1]?.method).toBe("POST");
    expect(useChatStore.getState().lockedUser).toBe("rain");
    expect(useChatStore.getState().authOk).toBe(false);
    expect(useChatStore.getState().draft).toBe("");
  });

  it("sends remember_me false by default and wipes private state on login failure", async () => {
    mocked.mockResolvedValue(json({ error: { message: "no" } }, 401));
    const ok = await useChatStore.getState().login("alpha", "correct-horse");
    expect(ok).toBe(false);
    const body = JSON.parse(String(mocked.mock.calls[0][1]?.body));
    expect(body.remember_me).toBe(false);
    expect(useChatStore.getState().draft).toBe("");
    expect(useChatStore.getState().conversations).toEqual([]);
  });
});

describe("chat store generation UI", () => {
  beforeEach(() => {
    mocked.mockReset();
    useChatStore.setState({
      messages: [],
      activeId: null,
      draft: "",
      streaming: false,
      error: null,
      controller: null,
      conversations: [],
      snapshot: null,
    });
  });

  it("keeps partial text and shows an abnormal terminal after transport EOF", async () => {
    chatThenConversations(
      'event: meta\ndata: {"conversation_id":"c1","message_id":"a1","user_message_id":"u1","created":true}\n\n' +
        'event: delta\ndata: {"content":"partial rain"}\n\n',
    );
    useChatStore.setState({ draft: "写长一点" });
    await useChatStore.getState().send();
    const asst = useChatStore.getState().messages.find((m) => m.role === "assistant");
    expect(asst?.content).toBe("partial rain");
    expect(asst?.status).toBe("interrupted");
    expect(asst?.incomplete).toBe(true);
    expect(asst?.finish_reason).toBe("interrupted_transport");
    expect(terminalCopy(asst?.finish_reason, asst?.terminal_state)).toBe("生成未正常完成");
    expect(isIncompleteTerminal(asst?.finish_reason, asst?.terminal_state)).toBe(true);
    expect(useChatStore.getState().error).toBeNull();
  });

  it("marks a user stop as abort without waiting for a reload", async () => {
    mocked.mockImplementation(async () => {
      throw new DOMException("Aborted", "AbortError");
    });
    useChatStore.setState({ draft: "停" });
    await useChatStore.getState().send();
    const asst = useChatStore.getState().messages.find((m) => m.role === "assistant");
    expect(asst?.status).toBe("interrupted");
    expect(asst?.incomplete).toBe(true);
    expect(asst?.finish_reason).toBe("abort");
    expect(asst?.terminal_state).toBe("interrupted_user");
    expect(terminalCopy(asst?.finish_reason, asst?.terminal_state)).toBe("已中断");
    expect(useChatStore.getState().error).toBeNull();
  });

  it("shows length copy without an error banner and keeps Continue eligible", async () => {
    chatThenConversations(
      'event: meta\ndata: {"conversation_id":"c1","message_id":"a1","user_message_id":"u1","created":true}\n\n' +
        'event: delta\ndata: {"content":"cut"}\n\n' +
        'event: done\ndata: {"finish_reason":"length","terminal_state":"completed_length","incomplete":false,"message":{"content":"cut"}}\n\n',
    );
    useChatStore.setState({ draft: "写很长" });
    await useChatStore.getState().send();
    const asst = useChatStore.getState().messages.find((m) => m.role === "assistant");
    expect(asst?.status).toBe("complete");
    expect(asst?.error).toBeUndefined();
    expect(useChatStore.getState().error).toBeNull();
    expect(terminalCopy(asst?.finish_reason, asst?.terminal_state)).toBe("已达到输出上限");
    expect(asst?.finish_reason === "length").toBe(true);
  });

  it("does not show error copy after a normal stop", async () => {
    chatThenConversations(
      'event: meta\ndata: {"conversation_id":"c1","message_id":"a1","user_message_id":"u1","created":true}\n\n' +
        'event: delta\ndata: {"content":"好"}\n\n' +
        'event: done\ndata: {"finish_reason":"stop","terminal_state":"completed_stop","incomplete":false,"message":{"content":"好"}}\n\n',
    );
    useChatStore.setState({ draft: "只回一个字：好" });
    await useChatStore.getState().send();
    const asst = useChatStore.getState().messages.find((m) => m.role === "assistant");
    expect(asst?.status).toBe("complete");
    expect(asst?.incomplete).toBe(false);
    expect(terminalCopy(asst?.finish_reason, asst?.terminal_state)).toBeNull();
    expect(useChatStore.getState().error).toBeNull();
  });

  it("regenerate replaces the last assistant instead of appending a second one", async () => {
    useChatStore.setState({
      activeId: "c1",
      messages: [
        { id: "u1", role: "user", content: "hi", status: "complete" },
        { id: "a1", role: "assistant", content: "old partial", status: "complete" },
      ],
    });
    chatThenConversations(
      'event: meta\ndata: {"conversation_id":"c1","message_id":"a2","user_message_id":"u1","created":false}\n\n' +
        'event: delta\ndata: {"content":"fresh"}\n\n' +
        'event: done\ndata: {"finish_reason":"stop","terminal_state":"completed_stop","incomplete":false,"message":{"content":"fresh"}}\n\n',
    );
    await useChatStore.getState().send("regenerate");
    const msgs = useChatStore.getState().messages;
    expect(msgs.filter((m) => m.role === "user")).toHaveLength(1);
    expect(msgs.filter((m) => m.role === "assistant")).toHaveLength(1);
    expect(msgs.at(-1)?.content).toBe("fresh");
    expect(msgs.some((m) => m.content === "old partial")).toBe(false);
  });

  it("continue grows the same assistant and does not insert a fake user", async () => {
    useChatStore.setState({
      activeId: "c1",
      messages: [
        { id: "u1", role: "user", content: "写长一点", status: "complete" },
        {
          id: "a1",
          role: "assistant",
          content: "partial",
          status: "complete",
          finish_reason: "length",
        },
      ],
    });
    chatThenConversations(
      'event: meta\ndata: {"conversation_id":"c1","message_id":"a1","user_message_id":"u1","created":false}\n\n' +
        'event: delta\ndata: {"content":" more"}\n\n' +
        'event: done\ndata: {"finish_reason":"stop","terminal_state":"completed_stop","incomplete":false,"message":{"content":"partial more"}}\n\n',
    );
    await useChatStore.getState().send("continue");
    const msgs = useChatStore.getState().messages;
    expect(msgs.filter((m) => m.role === "user").map((m) => m.content)).toEqual(["写长一点"]);
    expect(msgs.filter((m) => m.role === "assistant")).toHaveLength(1);
    expect(msgs.at(-1)?.id).toBe("a1");
    expect(msgs.at(-1)?.content).toBe("partial more");
    const body = JSON.parse(String((mocked.mock.calls[0][1] as RequestInit).body));
    expect(body.continue_generation).toBe(true);
    expect(body.message).toBe("");
  });

  it("keeps the last turn when Continue fails before meta", async () => {
    useChatStore.setState({
      activeId: "c1",
      messages: [
        { id: "u1", role: "user", content: "写长一点", status: "complete" },
        {
          id: "a1",
          role: "assistant",
          content: "partial",
          status: "complete",
          finish_reason: "length",
        },
      ],
    });
    mocked.mockImplementation(async (url: string) => {
      if (url === "/chat") return new Response("already completed", { status: 400 });
      if (String(url).startsWith("/conversation")) return json({ data: [] });
      throw new Error(`unmocked ${url}`);
    });
    await useChatStore.getState().send("continue");
    const msgs = useChatStore.getState().messages;
    expect(msgs.map((m) => m.id)).toEqual(["u1", "a1"]);
    expect(msgs.find((m) => m.id === "a1")?.content).toBe("partial");
    expect(useChatStore.getState().error).toBeTruthy();
  });

  it("keeps the last user turn when Regenerate fails before meta", async () => {
    useChatStore.setState({
      activeId: "c1",
      messages: [
        { id: "u1", role: "user", content: "hi", status: "complete" },
        { id: "a1", role: "assistant", content: "old partial", status: "complete" },
      ],
    });
    mocked.mockImplementation(async (url: string) => {
      if (url === "/chat") return new Response("model is busy", { status: 409 });
      if (String(url).startsWith("/conversation")) return json({ data: [] });
      throw new Error(`unmocked ${url}`);
    });
    await useChatStore.getState().send("regenerate");
    const msgs = useChatStore.getState().messages;
    expect(msgs.map((m) => m.id)).toEqual(["u1", "a1"]);
    expect(msgs.find((m) => m.id === "a1")?.content).toBe("old partial");
    expect(useChatStore.getState().error).toBeTruthy();
  });
});
