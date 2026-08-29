from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from typing import Any, AsyncIterator

from app.config import Settings
from app.db import get_conn
from app.providers.base import ChatChunk, ChatProvider, ChatRequest
from app.services.compress import compress_messages
from app.services.history import truncate_messages
from app.services.ingest import pack_user_message
from app.services.memory import MemoryService
from app.services.thinking import (
    normalize_effort,
    remap_assistant_for_history,
    split_thinking,
    thinking_budget_for,
)
from app.services.tokens import TokenEstimator


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id() -> str:
    return str(uuid.uuid4())


def heuristic_title(text: str) -> str:
    collapsed = " ".join(text.strip().split())
    if len(collapsed) <= 48:
        return collapsed or "New conversation"
    return collapsed[:48].rstrip() + "…"


class ChatService:
    def __init__(
        self,
        settings: Settings,
        provider: ChatProvider,
        tokenizer: TokenEstimator,
        memory: MemoryService | None = None,
    ):
        self.settings = settings
        self.provider = provider
        self.tokenizer = tokenizer
        self.memory = memory or MemoryService()
        self._lock = asyncio.Lock()
        self._busy: set[str] = set()

    def _conn(self) -> sqlite3.Connection:
        return get_conn()

    def list_conversations(
        self,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        conn = self._conn()
        needle = f"%{(q or '').strip()}%"
        where = "deleted_at IS NULL"
        args: list[Any] = []
        if owner_id:
            where += " AND user_id=?"
            args.append(owner_id)
        if q and q.strip():
            where += " AND (title LIKE ? OR last_message_preview LIKE ?)"
            args.extend([needle, needle])
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM conversations WHERE {where}",
            args,
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT id, title, model, created_at, updated_at, message_count,
                   last_message_preview, prompt_tokens_total, completion_tokens_total,
                   total_tokens
            FROM conversations
            WHERE {where}
            ORDER BY pinned DESC, updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [*args, limit, offset],
        ).fetchall()
        return {
            "object": "list",
            "total": total,
            "limit": limit,
            "offset": offset,
            "data": [dict(r) for r in rows],
        }

    def get_conversation(
        self, conversation_id: str, owner_id: str | None = None
    ) -> dict[str, Any] | None:
        conn = self._conn()
        if owner_id:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id=? AND deleted_at IS NULL AND user_id=?",
                (conversation_id, owner_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id=? AND deleted_at IS NULL",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        messages = conn.execute(
            """
            SELECT id, role, content, reasoning, status, prompt_tokens, completion_tokens,
                   cached_tokens, total_tokens, finish_reason, error, created_at
            FROM messages
            WHERE conversation_id=?
            ORDER BY seq ASC
            """,
            (conversation_id,),
        ).fetchall()
        data = dict(row)
        data["messages"] = [dict(m) for m in messages]
        data["system"] = data.get("system_prompt")
        return data

    def get_context(
        self, conversation_id: str, owner_id: str | None = None
    ) -> dict[str, Any] | None:
        if owner_id:
            conv = self._conn().execute(
                "SELECT id FROM conversations WHERE id=? AND deleted_at IS NULL AND user_id=?",
                (conversation_id, owner_id),
            ).fetchone()
        else:
            conv = self._conn().execute(
                "SELECT id FROM conversations WHERE id=? AND deleted_at IS NULL",
                (conversation_id,),
            ).fetchone()
        if conv is None:
            return None
        snap = self._conn().execute(
            """
            SELECT * FROM context_snapshots
            WHERE conversation_id=?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        if snap is None:
            return {
                "conversation_id": conversation_id,
                "snapshot": None,
            }
        row = dict(snap)
        row["payload"] = json.loads(row["payload_json"])
        row["tokens"] = json.loads(row["tokens_json"] or "{}")
        row["dropped_message_ids"] = json.loads(row["dropped_message_ids_json"] or "[]")
        row["memory_ids"] = json.loads(row["memory_ids_json"] or "[]")
        del row["payload_json"]
        del row["tokens_json"]
        del row["dropped_message_ids_json"]
        del row["memory_ids_json"]
        return row

    def delete_conversation(self, conversation_id: str, owner_id: str | None = None) -> bool:
        conn = self._conn()
        if owner_id:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id=? AND user_id=?",
                (conversation_id, owner_id),
            )
        else:
            cur = conn.execute(
                "DELETE FROM conversations WHERE id=?",
                (conversation_id,),
            )
        conn.commit()
        return cur.rowcount > 0

    def rename_conversation(
        self, conversation_id: str, title: str, owner_id: str | None = None
    ) -> bool:
        conn = self._conn()
        if owner_id:
            cur = conn.execute(
                """
                UPDATE conversations
                SET title=?, title_source='user', updated_at=?
                WHERE id=? AND deleted_at IS NULL AND user_id=?
                """,
                (title.strip(), now_ms(), conversation_id, owner_id),
            )
        else:
            cur = conn.execute(
                """
                UPDATE conversations
                SET title=?, title_source='user', updated_at=?
                WHERE id=? AND deleted_at IS NULL
                """,
                (title.strip(), now_ms(), conversation_id),
            )
        conn.commit()
        return cur.rowcount > 0

    def global_context(self) -> dict[str, Any]:
        return {
            "model": self.settings.model_name,
            "provider": self.provider.name,
            "context_window": self.settings.context_window,
            "practical_prompt_budget": self.settings.practical_prompt_budget,
            "default_max_tokens": self.settings.default_max_tokens,
            "max_tokens_cap": self.settings.max_tokens_cap,
            "default_system": self.settings.default_system,
            "enable_thinking": self.settings.enable_thinking,
            "reasoning_effort": self.settings.reasoning_effort,
            "tokenizer": self.tokenizer.method,
            "overflow_policy": self.settings.overflow_policy,
        }

    def _create_conversation(
        self, system: str, model: str, settings_json: str, owner_id: str | None = None
    ) -> str:
        cid = new_id()
        ts = now_ms()
        conn = self._conn()
        conn.execute(
            """
            INSERT INTO conversations (
              id, title, title_source, model, system_prompt, settings_json,
              created_at, updated_at, user_id
            ) VALUES (?, ?, 'auto', ?, ?, ?, ?, ?, ?)
            """,
            (cid, "New conversation", model, system, settings_json, ts, ts, owner_id),
        )
        if (system or "").strip():
            conn.execute(
                """
                INSERT INTO messages (
                  id, conversation_id, seq, role, content, status, created_at, updated_at
                ) VALUES (?, ?, 0, 'system', ?, 'complete', ?, ?)
                """,
                (new_id(), cid, system, ts, ts),
            )
        conn.commit()
        return cid

    def drop_last_assistant(self, conversation_id: str) -> bool:
        conn = self._conn()
        row = conn.execute(
            """
            SELECT id FROM messages
            WHERE conversation_id=? AND role='assistant'
            ORDER BY seq DESC LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM messages WHERE id=?", (row["id"],))
        conn.commit()
        return True

    def _next_seq(self, conversation_id: str) -> int:
        row = self._conn().execute(
            "SELECT COALESCE(MAX(seq), -1) AS m FROM messages WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
        return int(row["m"]) + 1

    def _insert_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        reasoning: str | None = None,
        status: str = "complete",
        seq: int | None = None,
    ) -> tuple[str, int]:
        mid = new_id()
        ts = now_ms()
        seq = self._next_seq(conversation_id) if seq is None else seq
        self._conn().execute(
            """
            INSERT INTO messages (
              id, conversation_id, seq, role, content, reasoning, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mid, conversation_id, seq, role, content, reasoning, status, ts, ts),
        )
        self._conn().commit()
        return mid, seq

    def _load_history(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = self._conn().execute(
            """
            SELECT id, role, content, reasoning
            FROM messages
            WHERE conversation_id=? AND status IN ('complete', 'cancelled', 'streaming', 'pending')
            ORDER BY seq ASC
            """,
            (conversation_id,),
        ).fetchall()
        out = []
        for r in rows:
            item = {"id": r["id"], "role": r["role"], "content": r["content"] or ""}
            if r["reasoning"]:
                item["reasoning"] = r["reasoning"]
            out.append(item)
        return out

    def _build_payload(
        self,
        history: list[dict[str, Any]],
        *,
        max_tokens: int,
        enable_thinking: bool,
        reasoning_effort: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        estimate = self.tokenizer.count_text
        budget = self.settings.practical_prompt_budget
        # Prompt budget is independent of the completion cap. Qwen3.5 native
        # context is 262k; stealing max_tokens from an 8k window was cutting 1万字 inputs.
        history, history_summary, compressed = compress_messages(
            history,
            budget=budget,
            estimate=estimate,
            reserved_output=0,
            recent_keep=8,
        )
        kept, dropped, truncated = truncate_messages(
            history, budget=budget, estimate=estimate, reserved_output=0
        )
        last_user = next((m.get("content") or "" for m in reversed(kept) if m.get("role") == "user"), "")
        memories = self.memory.retrieve("", last_user, 256)
        fence = self.memory.fence(memories)
        sent: list[dict[str, Any]] = []
        system_text = ""
        last_user_idx = None
        for i, msg in enumerate(kept):
            role = msg["role"]
            if role == "system":
                text = (msg.get("content") or "").strip()
                if not text:
                    continue
                system_text = text
                sent.append({"role": "system", "content": text})
                continue
            if role == "assistant":
                sent.append(
                    remap_assistant_for_history(
                        {
                            "role": "assistant",
                            "content": msg.get("content") or "",
                            "reasoning": "" if not self.settings.preserve_thinking else msg.get("reasoning"),
                        }
                    )
                )
                continue
            if role == "user":
                last_user_idx = len(sent)
                sent.append({"role": "user", "content": msg.get("content") or ""})
                continue
            sent.append({"role": role, "content": msg.get("content") or ""})

        document_pack = None
        if last_user_idx is not None:
            others = [m for i, m in enumerate(sent) if i != last_user_idx]
            used = self.tokenizer.count_messages(others) if others else 0
            room = max(256, budget - used)
            packed = pack_user_message(sent[last_user_idx]["content"] or "", room, estimate)
            if packed.applied:
                sent[last_user_idx]["content"] = packed.text
                document_pack = {
                    "applied": True,
                    "original_tokens": packed.original_tokens,
                    "kept_tokens": packed.kept_tokens,
                    "chunks_total": packed.chunks_total,
                    "chunks_kept": packed.chunks_kept,
                }

        if fence and last_user_idx is not None:
            sent[last_user_idx]["content"] = (
                fence + "\n\n" + (sent[last_user_idx].get("content") or "")
            )

        prompt_tokens = self.tokenizer.count_messages(sent)
        snapshot = {
            "effective_system_prompt": system_text,
            "sent_messages": sent,
            "truncated": truncated or compressed,
            "compressed": compressed,
            "history_summary": history_summary,
            "dropped_message_ids": dropped,
            "memory_ids": [m.id for m in memories],
            "occupancy": {
                "effective_window_tokens": budget,
                "model_max_tokens": self.settings.context_window,
                "prompt_tokens": prompt_tokens,
                "completion_budget": max_tokens,
                "reserved_output_tokens": max_tokens,
                "ratio": prompt_tokens / budget if budget else 0,
                "document_pack": document_pack,
            },
            "params": {
                "enable_thinking": enable_thinking,
                "reasoning_effort": reasoning_effort,
                "preserve_thinking": self.settings.preserve_thinking,
            },
        }
        return sent, snapshot

    def _save_snapshot(
        self, conversation_id: str, snapshot: dict[str, Any], params: dict[str, Any]
    ) -> str:
        sid = new_id()
        payload = {
            "model": "default_model",
            "messages": snapshot["sent_messages"],
            **params,
        }
        tokens = {
            "prompt_estimated": snapshot["occupancy"]["prompt_tokens"],
            "prompt_actual": None,
            "completion_actual": None,
            "source": self.tokenizer.method,
        }
        self._conn().execute(
            """
            INSERT INTO context_snapshots (
              id, conversation_id, payload_json, effective_system_prompt,
              tokens_json, truncated, dropped_message_ids_json, memory_ids_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                conversation_id,
                json.dumps(payload, ensure_ascii=False),
                snapshot["effective_system_prompt"],
                json.dumps(tokens),
                1 if snapshot["truncated"] else 0,
                json.dumps(snapshot["dropped_message_ids"]),
                json.dumps(snapshot["memory_ids"]),
                now_ms(),
            ),
        )
        self._conn().commit()
        snapshot["snapshot_id"] = sid
        snapshot["payload"] = payload
        snapshot["tokens"] = tokens
        return sid

    def _finalize_assistant(
        self,
        *,
        conversation_id: str,
        assistant_id: str,
        user_id: str,
        content: str,
        reasoning: str,
        status: str,
        finish_reason: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int,
        snapshot_id: str,
        model: str,
        params: dict[str, Any],
        error: str | None = None,
        started_ms: int,
        user_preview: str,
        is_new: bool,
    ) -> None:
        ts = now_ms()
        total = prompt_tokens + completion_tokens
        conn = self._conn()
        conn.execute(
            """
            UPDATE messages SET
              content=?, reasoning=?, status=?, finish_reason=?, error=?,
              prompt_tokens=?, completion_tokens=?, cached_tokens=?, total_tokens=?,
              updated_at=?
            WHERE id=?
            """,
            (
                content,
                reasoning or None,
                status,
                finish_reason,
                error,
                prompt_tokens,
                completion_tokens,
                cached_tokens,
                total,
                ts,
                assistant_id,
            ),
        )
        run_id = new_id()
        conn.execute(
            """
            INSERT INTO generation_runs (
              id, conversation_id, message_id, snapshot_id, model, params_json,
              prompt_tokens, completion_tokens, cached_tokens, total_tokens,
              finish_reason, latency_ms, error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                conversation_id,
                assistant_id,
                snapshot_id,
                model,
                json.dumps(params),
                prompt_tokens,
                completion_tokens,
                cached_tokens,
                total,
                finish_reason,
                ts - started_ms,
                error,
                ts,
            ),
        )
        conn.execute(
            "UPDATE context_snapshots SET generation_run_id=? WHERE id=?",
            (run_id, snapshot_id),
        )
        tokens_json = json.dumps(
            {
                "prompt_estimated": prompt_tokens,
                "prompt_actual": prompt_tokens,
                "completion_actual": completion_tokens,
                "cached_tokens": cached_tokens,
                "source": "upstream" if prompt_tokens else self.tokenizer.method,
            }
        )
        conn.execute(
            "UPDATE context_snapshots SET tokens_json=? WHERE id=?",
            (tokens_json, snapshot_id),
        )
        title = heuristic_title(user_preview) if is_new else None
        conn.execute(
            """
            UPDATE conversations SET
              prompt_tokens_total = prompt_tokens_total + ?,
              completion_tokens_total = completion_tokens_total + ?,
              total_tokens = total_tokens + ?,
              last_message_preview=?,
              updated_at=?,
              title = CASE WHEN title_source='auto' AND ? IS NOT NULL THEN ? ELSE title END,
              message_count = (
                SELECT COUNT(*) FROM messages
                WHERE conversation_id=? AND role != 'system'
              )
            WHERE id=?
            """,
            (
                prompt_tokens,
                completion_tokens,
                total,
                user_preview[:160],
                ts,
                title,
                title,
                conversation_id,
                conversation_id,
            ),
        )
        conn.commit()

    async def chat(
        self,
        *,
        message: str,
        conversation_id: str | None,
        stream: bool,
        regenerate: bool = False,
        system: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool | None = None,
        reasoning_effort: str | None = None,
        owner_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        s = self.settings
        text = (message or "").strip()
        skip_user_insert = False
        if regenerate:
            if not conversation_id:
                yield {
                    "event": "error",
                    "data": {
                        "error": {
                            "message": "conversation_id required to regenerate",
                            "type": "invalid_request_error",
                            "code": "invalid_body",
                            "param": "conversation_id",
                        }
                    },
                    "status": 400,
                }
                return
            existing = self.get_conversation(conversation_id, owner_id=owner_id)
            if existing is None:
                yield {
                    "event": "error",
                    "data": {
                        "error": {
                            "message": "conversation not found",
                            "type": "not_found_error",
                            "code": "conversation_not_found",
                        }
                    },
                    "status": 404,
                }
                return
            users = [m for m in existing["messages"] if m["role"] == "user"]
            if not users:
                yield {
                    "event": "error",
                    "data": {
                        "error": {
                            "message": "no user turn to regenerate",
                            "type": "invalid_request_error",
                            "code": "invalid_body",
                        }
                    },
                    "status": 400,
                }
                return
            text = (users[-1].get("content") or "").strip()
            self.drop_last_assistant(conversation_id)
            skip_user_insert = True
        elif not text:
            yield {
                "event": "error",
                "data": {
                    "error": {
                        "message": "message is required",
                        "type": "invalid_request_error",
                        "code": "invalid_body",
                        "param": "message",
                    }
                },
                "status": 400,
            }
            return
        if len(text) > s.max_message_chars:
            yield {
                "event": "error",
                "data": {
                    "error": {
                        "message": "message too long",
                        "type": "invalid_request_error",
                        "code": "invalid_body",
                        "param": "message",
                    }
                },
                "status": 400,
            }
            return
        temperature = s.default_temperature if temperature is None else temperature
        top_p = s.default_top_p if top_p is None else top_p
        top_k = s.default_top_k if top_k is None else top_k
        max_tokens = s.default_max_tokens if max_tokens is None else max_tokens
        max_tokens = max(1, min(int(max_tokens), s.max_tokens_cap))
        enable_thinking = s.enable_thinking if enable_thinking is None else enable_thinking
        effort = normalize_effort(reasoning_effort or s.reasoning_effort)
        system_prompt = (system if system is not None else s.default_system) or ""
        params = {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "max_tokens": max_tokens,
            "enable_thinking": enable_thinking,
            "reasoning_effort": effort,
            "thinking_budget": thinking_budget_for(
                effort,
                low=s.thinking_budget_low,
                medium=s.thinking_budget_medium,
                xhigh=s.thinking_budget_xhigh,
            ),
        }

        created = False
        if conversation_id:
            existing = self.get_conversation(conversation_id, owner_id=owner_id)
            if existing is None:
                yield {
                    "event": "error",
                    "data": {
                        "error": {
                            "message": "conversation not found",
                            "type": "not_found_error",
                            "code": "conversation_not_found",
                        }
                    },
                    "status": 404,
                }
                return
            cid = conversation_id
        else:
            cid = self._create_conversation(
                system_prompt, s.model_name, json.dumps(params), owner_id=owner_id
            )
            created = True

        if cid in self._busy:
            yield {
                "event": "error",
                "data": {
                    "error": {
                        "message": "generation already in progress",
                        "type": "invalid_request_error",
                        "code": "generation_in_progress",
                    }
                },
                "status": 409,
            }
            return

        async with self._lock:
            if len(self._busy) >= s.generation_concurrency:
                yield {
                    "event": "error",
                    "data": {
                        "error": {
                            "message": "model is busy",
                            "type": "invalid_request_error",
                            "code": "generation_in_progress",
                        }
                    },
                    "status": 409,
                }
                return
            self._busy.add(cid)

        started = now_ms()
        user_id = ""
        assistant_id = ""
        snapshot_id = ""
        content_buf = ""
        reasoning_buf = ""
        finish = "stop"
        prompt_tokens = 0
        completion_tokens = 0
        cached_tokens = 0
        usage_source = "estimated"
        status = "complete"
        error = None
        occupancy: dict[str, Any] = {}
        try:
            if skip_user_insert:
                hist = self._load_history(cid)
                last_u = next((m for m in reversed(hist) if m.get("role") == "user"), None)
                user_id = (last_u or {}).get("id") or ""
            else:
                user_id, _ = self._insert_message(cid, "user", text)
            assistant_id, _ = self._insert_message(
                cid, "assistant", "", status="streaming"
            )
            history = self._load_history(cid)
            history = [m for m in history if m["id"] != assistant_id]
            sent, snapshot_meta = self._build_payload(
                history,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
                reasoning_effort=effort,
            )
            occupancy = snapshot_meta["occupancy"]
            prompt_tokens = occupancy["prompt_tokens"]
            if (
                occupancy["prompt_tokens"] + max_tokens > s.context_window
                and s.overflow_policy == "error"
            ):
                status = "error"
                finish = "error"
                error = "prompt exceeds practical context budget"
                return

            snapshot_id = self._save_snapshot(cid, snapshot_meta, params)
            yield {
                "event": "meta",
                "data": {
                    "conversation_id": cid,
                    "created": created,
                    "user_message_id": user_id,
                    "message_id": assistant_id,
                    "model": s.model_name,
                },
            }
            yield {
                "event": "snapshot",
                "data": {
                    "request_id": snapshot_id,
                    "conversation_id": cid,
                    "model": s.model_name,
                    "params": params,
                    "effective_system_prompt": snapshot_meta["effective_system_prompt"],
                    "sent_messages": snapshot_meta["sent_messages"],
                    "occupancy": occupancy,
                    "truncation": {
                        "applied": snapshot_meta["truncated"],
                        "policy": "drop_oldest" if snapshot_meta["truncated"] else "none",
                        "dropped_message_ids": snapshot_meta["dropped_message_ids"],
                    },
                },
            }

            req = ChatRequest(
                messages=sent,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
                reasoning_effort=effort,
                preserve_thinking=s.preserve_thinking,
            )

            if not stream:
                think_budget = thinking_budget_for(
                    effort,
                    low=s.thinking_budget_low,
                    medium=s.thinking_budget_medium,
                    xhigh=s.thinking_budget_xhigh,
                )
                first_max = max_tokens
                if think_budget and enable_thinking:
                    first_max = min(max_tokens, think_budget)
                first_req = ChatRequest(
                    messages=sent,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    max_tokens=first_max,
                    enable_thinking=enable_thinking,
                    reasoning_effort=effort,
                    preserve_thinking=s.preserve_thinking,
                )
                result = await self.provider.complete(first_req)
                content_buf = result.content
                reasoning_buf = result.reasoning
                if not reasoning_buf and content_buf:
                    content_buf, reasoning_buf = split_thinking(content_buf)
                if (
                    think_budget
                    and enable_thinking
                    and not content_buf
                    and hasattr(self.provider, "complete_after_think")
                ):
                    leftover = max(1, max_tokens - self.tokenizer.count_text(reasoning_buf))
                    extra = await self.provider.complete_after_think(
                        first_req, reasoning_buf, leftover
                    )
                    content_buf = extra.content
                    result = extra
                finish = result.finish_reason
                if result.prompt_tokens is not None:
                    prompt_tokens = result.prompt_tokens
                    usage_source = result.usage_source
                if result.completion_tokens:
                    completion_tokens = result.completion_tokens
                else:
                    completion_tokens = self.tokenizer.count_text(
                        (reasoning_buf or "") + (content_buf or "")
                    )
                cached_tokens = result.cached_tokens
                if content_buf:
                    yield {"event": "delta", "data": {"content": content_buf}}
                if reasoning_buf:
                    yield {"event": "delta", "data": {"reasoning": reasoning_buf}}
            else:
                think_budget = thinking_budget_for(
                    effort,
                    low=s.thinking_budget_low,
                    medium=s.thinking_budget_medium,
                    xhigh=s.thinking_budget_xhigh,
                )
                think_cut = False
                agen = self.provider.stream(req)
                try:
                    async for chunk in agen:
                        if chunk.keepalive:
                            yield {"event": "ping", "data": {"keepalive": chunk.keepalive}}
                            continue
                        if chunk.delta_reasoning:
                            reasoning_buf += chunk.delta_reasoning
                            yield {
                                "event": "delta",
                                "data": {"reasoning": chunk.delta_reasoning},
                            }
                            if (
                                think_budget
                                and enable_thinking
                                and not content_buf
                                and self.tokenizer.count_text(reasoning_buf) >= think_budget
                            ):
                                think_cut = True
                                break
                        if chunk.delta_content:
                            content_buf += chunk.delta_content
                            yield {
                                "event": "delta",
                                "data": {"content": chunk.delta_content},
                            }
                        if chunk.finish_reason:
                            finish = chunk.finish_reason
                        if chunk.prompt_tokens is not None:
                            prompt_tokens = chunk.prompt_tokens
                            usage_source = "upstream"
                        if chunk.completion_tokens is not None:
                            completion_tokens = chunk.completion_tokens
                            usage_source = "upstream"
                        if chunk.cached_tokens is not None:
                            cached_tokens = chunk.cached_tokens
                finally:
                    closer = getattr(agen, "aclose", None)
                    if closer is not None:
                        await closer()
                if think_cut and not content_buf and hasattr(self.provider, "stream_after_think"):
                    leftover = max(1, max_tokens - self.tokenizer.count_text(reasoning_buf))
                    async for chunk in self.provider.stream_after_think(req, reasoning_buf, leftover):
                        if chunk.keepalive:
                            yield {"event": "ping", "data": {"keepalive": chunk.keepalive}}
                            continue
                        if chunk.delta_content:
                            content_buf += chunk.delta_content
                            yield {
                                "event": "delta",
                                "data": {"content": chunk.delta_content},
                            }
                        if chunk.finish_reason:
                            finish = chunk.finish_reason
                        if chunk.prompt_tokens is not None:
                            prompt_tokens = chunk.prompt_tokens
                            usage_source = "upstream"
                        if chunk.completion_tokens is not None:
                            completion_tokens = chunk.completion_tokens
                            usage_source = "upstream"
                        if chunk.cached_tokens is not None:
                            cached_tokens = chunk.cached_tokens
                if not reasoning_buf and content_buf:
                    content_buf, reasoning_buf = split_thinking(content_buf)
                if not completion_tokens:
                    completion_tokens = self.tokenizer.count_text(
                        (reasoning_buf or "") + (content_buf or "")
                    )
        except (asyncio.CancelledError, GeneratorExit):
            status = "cancelled"
            finish = "abort"
            error = "cancelled"
            raise
        except TimeoutError as exc:
            status = "error"
            finish = "error"
            error = str(exc)
        except ConnectionError as exc:
            status = "error"
            finish = "error"
            error = str(exc)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            finish = "error"
            error = str(exc)
        finally:
            try:
                if assistant_id:
                    if not snapshot_id:
                        snapshot_id = self._save_snapshot(
                            cid,
                            {
                                "sent_messages": [],
                                "effective_system_prompt": system_prompt,
                                "occupancy": occupancy
                                or {
                                    "prompt_tokens": 0,
                                    "effective_window_tokens": s.practical_prompt_budget,
                                },
                                "truncated": False,
                                "dropped_message_ids": [],
                                "memory_ids": [],
                            },
                            params,
                        )
                    self._finalize_assistant(
                        conversation_id=cid,
                        assistant_id=assistant_id,
                        user_id=user_id,
                        content=content_buf,
                        reasoning=reasoning_buf,
                        status="cancelled" if status == "cancelled" else status,
                        finish_reason="abort" if status == "cancelled" else finish,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens
                        or self.tokenizer.count_text(reasoning_buf + content_buf),
                        cached_tokens=cached_tokens,
                        snapshot_id=snapshot_id,
                        model=s.model_name,
                        params=params,
                        error=error,
                        started_ms=started,
                        user_preview=text,
                        is_new=created,
                    )
            finally:
                self._busy.discard(cid)

        if error and status == "error":
            overflow = "exceeds practical context" in (error or "")
            yield {
                "event": "error",
                "data": {
                    "error": {
                        "message": error,
                        "type": "context_length_exceeded" if overflow else "api_error",
                        "code": "context_overflow" if overflow else "upstream_error",
                    }
                },
                "status": 413 if overflow else 502,
            }
            return

        usage = {
            "input": prompt_tokens,
            "output": completion_tokens,
            "total": prompt_tokens + completion_tokens,
            "cached": cached_tokens,
            "source": usage_source,
        }
        yield {"event": "usage", "data": usage}
        yield {
            "event": "done",
            "data": {
                "finish_reason": finish,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "prompt_tokens_source": usage_source,
                },
                "message": {
                    "id": assistant_id,
                    "role": "assistant",
                    "content": content_buf,
                    "reasoning_content": reasoning_buf or None,
                },
            },
        }
