from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
import uuid
from typing import Any, AsyncIterator

from app.config import Settings
from app.db import get_conn
from app.providers.base import ChatChunk, ChatProvider, ChatRequest
from app.services.continuation import (
    TailStripper,
    continue_assistant_message,
    strip_regenerated_tail,
)
from app.services.dialogue_context import DialogueState, build_dialogue_context
from app.services.history import truncate_messages
from app.services.inference_watch import InferenceWatch
from app.services.answer_verify import verify_answer
from app.services.context_route import extractive_compress, route_document
from app.services.ingest import pack_user_message, requests_full_document, split_query_and_body
from app.services.memory import MemoryService
from app.services.profiles import resolve_profile
from app.services.repetition import hard_self_loop
from app.services.sampling import THINKING, resolve_sampling
from app.services.stream_protocol import COMPLETE_STATES, StreamLedger, TerminalState
from app.services.thinking import (
    normalize_effort,
    remap_assistant_for_history,
    split_thinking,
    thinking_budget_for,
    thinking_token_split,
)
from app.services.tokens import TokenEstimator


def now_ms() -> int:
    return int(time.time() * 1000)


def _public_message(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    raw = item.pop("metadata_json", None)
    if not raw:
        return item
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError:
        return item
    check = meta.get("answer_check") if isinstance(meta, dict) else None
    if isinstance(check, dict):
        item["answer_check"] = check
    return item


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
        self.memory = memory or MemoryService(settings)
        if getattr(self.memory, "settings", None) is None:
            self.memory.settings = settings
        self._lock = asyncio.Lock()
        self._busy: set[str] = set()
        self.watch = InferenceWatch()

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
        from app.security import tenant_requires_owner

        if not owner_id and tenant_requires_owner(self.settings):
            return {"object": "list", "total": 0, "limit": limit, "offset": offset, "data": []}
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
        from app.security import tenant_requires_owner

        conn = self._conn()
        if not owner_id and tenant_requires_owner(self.settings):
            return None
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
                   cached_tokens, total_tokens, finish_reason, error, created_at,
                   metadata_json
            FROM messages
            WHERE conversation_id=?
            ORDER BY seq ASC
            """,
            (conversation_id,),
        ).fetchall()
        data = dict(row)
        data["messages"] = [_public_message(m) for m in messages]
        data["system"] = data.get("system_prompt")
        return data

    def get_context(
        self, conversation_id: str, owner_id: str | None = None
    ) -> dict[str, Any] | None:
        from app.security import tenant_requires_owner

        if not owner_id and tenant_requires_owner(self.settings):
            return None
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
        from app.security import tenant_requires_owner

        if not owner_id and tenant_requires_owner(self.settings):
            return False
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

    def delete_message(
        self, conversation_id: str, message_id: str, owner_id: str | None = None
    ) -> bool:
        conn = self._conn()
        if owner_id:
            conversation = conn.execute(
                "SELECT id FROM conversations WHERE id=? AND user_id=?",
                (conversation_id, owner_id),
            ).fetchone()
            if conversation is None:
                return False
        row = conn.execute(
            "SELECT seq, role FROM messages WHERE id=? AND conversation_id=?",
            (message_id, conversation_id),
        ).fetchone()
        if row is None:
            return False
        if row["role"] == "user":
            next_user = conn.execute(
                """
                SELECT MIN(seq) AS seq FROM messages
                WHERE conversation_id=? AND role='user' AND seq>?
                """,
                (conversation_id, row["seq"]),
            ).fetchone()["seq"]
            if next_user is None:
                conn.execute("DELETE FROM messages WHERE conversation_id=? AND seq>=?", (conversation_id, row["seq"]))
            else:
                conn.execute(
                    "DELETE FROM messages WHERE conversation_id=? AND seq>=? AND seq<?",
                    (conversation_id, row["seq"], next_user),
                )
        else:
            conn.execute("DELETE FROM messages WHERE id=?", (message_id,))
        stats = conn.execute(
            """
            SELECT COUNT(*) AS count,
                   COALESCE(SUM(prompt_tokens), 0) AS prompt,
                   COALESCE(SUM(completion_tokens), 0) AS completion,
                   COALESCE(SUM(total_tokens), 0) AS total
            FROM messages WHERE conversation_id=?
            """,
            (conversation_id,),
        ).fetchone()
        preview = conn.execute(
            """
            SELECT content FROM messages
            WHERE conversation_id=? AND role='user'
            ORDER BY seq DESC LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        conn.execute("DELETE FROM context_snapshots WHERE conversation_id=?", (conversation_id,))
        conn.execute(
            """
            UPDATE conversations
            SET message_count=?, prompt_tokens_total=?, completion_tokens_total=?, total_tokens=?,
                last_message_preview=?, updated_at=?
            WHERE id=?
            """,
            (
                stats["count"],
                stats["prompt"],
                stats["completion"],
                stats["total"],
                preview["content"][:240] if preview else None,
                now_ms(),
                conversation_id,
            ),
        )
        conn.commit()
        return True

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

    def note_inference_success(self, method: str = "user_generation") -> None:
        self.watch.note_success(method)

    def note_inference_timeout(self, message: str | None = None) -> None:
        self.watch.note_timeout(message)

    def note_inference_failure(self, message: str | None = None) -> None:
        self.watch.note_failure(message)

    def inference_status(self, *, busy: bool = False) -> dict[str, Any]:
        snap = self.watch.snapshot()
        capability = self.watch.capability(busy=busy)
        return {
            "ready": capability == "READY",
            "consecutive_timeouts": snap["consecutive_timeouts"],
            "last_error": snap["last_error"],
            "last_verified_at": snap["last_verified_at"],
            "capability": capability,
            "verification_method": snap["verification_method"],
            "evidence_expires_at": snap["evidence_expires_at"],
        }

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
            "default_profile": self.settings.default_profile,
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
            WHERE conversation_id=? AND status IN ('complete', 'cancelled', 'streaming', 'pending', 'error')
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

    def _conversation_settings(self, conversation_id: str) -> dict[str, Any]:
        row = self._conn().execute(
            "SELECT settings_json FROM conversations WHERE id=?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            return {}
        try:
            data = json.loads(row["settings_json"] or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _load_dialogue_meta(self, conversation_id: str) -> tuple[DialogueState, str | None]:
        data = self._conversation_settings(conversation_id)
        raw = data.get("dialogue_state") if isinstance(data.get("dialogue_state"), dict) else {}
        allowed = DialogueState().__dict__.keys()
        state = DialogueState(**{k: raw[k] for k in allowed if k in raw})
        summary = data.get("rolling_summary")
        return state, summary if isinstance(summary, str) else None

    def _save_dialogue_meta(
        self,
        conversation_id: str,
        *,
        state: DialogueState,
        summary: str | None,
        params: dict[str, Any],
    ) -> None:
        current = self._conversation_settings(conversation_id)
        payload = {
            **params,
            "dialogue_state": state.__dict__,
            "rolling_summary": summary,
        }
        used = current.get("continue_completion_prompts")
        if isinstance(used, list):
            payload["continue_completion_prompts"] = used
        self._conn().execute(
            "UPDATE conversations SET settings_json=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), conversation_id),
        )
        self._conn().commit()

    def _used_continue_prompts(self, conversation_id: str) -> list[str]:
        data = self._conversation_settings(conversation_id)
        raw = data.get("continue_completion_prompts") or []
        return [p for p in raw if isinstance(p, str)][-16:]

    def _remember_continue_prompt(self, conversation_id: str, prompt: str) -> None:
        if not prompt:
            return
        used = self._used_continue_prompts(conversation_id)
        if prompt not in used:
            used.append(prompt)
        data = self._conversation_settings(conversation_id)
        data["continue_completion_prompts"] = used[-16:]
        self._conn().execute(
            "UPDATE conversations SET settings_json=? WHERE id=?",
            (json.dumps(data, ensure_ascii=False), conversation_id),
        )
        self._conn().commit()

    def _clear_continue_prompts(self, conversation_id: str) -> None:
        data = self._conversation_settings(conversation_id)
        if not data.get("continue_completion_prompts"):
            return
        data["continue_completion_prompts"] = []
        self._conn().execute(
            "UPDATE conversations SET settings_json=? WHERE id=?",
            (json.dumps(data, ensure_ascii=False), conversation_id),
        )
        self._conn().commit()

    def _build_payload(
        self,
        history: list[dict[str, Any]],
        *,
        max_tokens: int,
        enable_thinking: bool,
        reasoning_effort: str,
        conversation_id: str,
        owner_id: str | None,
        prior_state: DialogueState | None = None,
        prior_summary: str | None = None,
        prompt_budget: int | None = None,
        prompt_soft_target: int | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        estimate = self.tokenizer.count_text
        budget = prompt_budget or self.settings.practical_prompt_budget
        latest_user_content = next(
            (m.get("content") or "" for m in reversed(history) if m.get("role") == "user"),
            "",
        )
        full_document = requests_full_document(latest_user_content)
        if full_document:
            budget = self.settings.practical_prompt_budget
        built = build_dialogue_context(
            history,
            budget=budget,
            estimate=estimate,
            prior_state=prior_state,
            prior_summary=prior_summary,
            recent_turn_target=8,
            min_recent_turns=4,
            fold_every_turns=4,
        )
        kept, dropped, truncated = truncate_messages(
            built.messages, budget=budget, estimate=estimate, reserved_output=0
        )
        last_user = next(
            (
                m.get("content") or ""
                for m in reversed(kept)
                if m.get("role") == "user" and m.get("id") != "dialogue-context"
            ),
            "",
        )
        memories = self.memory.retrieve(
            conversation_id,
            last_user,
            256,
            owner_id=owner_id,
        )
        fence = self.memory.fence(memories)
        sent: list[dict[str, Any]] = []
        system_text = ""
        last_user_idx = None
        for msg in kept:
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
                if msg.get("id") != "dialogue-context":
                    last_user_idx = len(sent)
                sent.append({"role": "user", "content": msg.get("content") or ""})
                continue
            sent.append({"role": role, "content": msg.get("content") or ""})

        document_pack = None
        if last_user_idx is not None:
            others = [m for i, m in enumerate(sent) if i != last_user_idx]
            used = self.tokenizer.count_messages(others) if others else 0
            room = max(256, budget - used)
            original = sent[last_user_idx]["content"] or ""
            query, body = split_query_and_body(original)
            target = body if query else original
            question = query or (original.split("\n", 1)[0][:200] if original else "")
            query_cost = (estimate(query) + 8) if query else 0
            room_for_body = max(64, room - query_cost)

            if full_document:
                packed = pack_user_message(original, room, estimate)
                if packed.applied:
                    raise ValueError("full document exceeds practical context budget")
                document_pack = {
                    "applied": False,
                    "original_tokens": packed.original_tokens,
                    "kept_tokens": packed.kept_tokens,
                    "chunks_total": packed.chunks_total,
                    "chunks_kept": packed.chunks_kept,
                    "context_route": {
                        "mode": "verbatim",
                        "archive_sha256": hashlib.sha256(target.encode("utf-8")).hexdigest(),
                        "original_chars": len(target),
                        "served_chars": len(target),
                        "silent_truncation": False,
                        "fallback_reason": None,
                        "citations": [],
                    },
                }
            else:
                target_tokens = estimate(target) if target else 0
                if target_tokens <= room_for_body:
                    document_pack = {
                        "applied": False,
                        "original_tokens": target_tokens,
                        "kept_tokens": target_tokens,
                        "chunks_total": 1,
                        "chunks_kept": 1,
                        "context_route": {
                            "mode": "verbatim",
                            "archive_sha256": hashlib.sha256(target.encode("utf-8")).hexdigest(),
                            "original_chars": len(target),
                            "served_chars": len(target),
                            "silent_truncation": False,
                            "fallback_reason": None,
                            "citations": [],
                        },
                    }
                else:
                    max_chars = max(400, min(len(target), room_for_body * 3))

                    def _compress(src: str) -> str:
                        return extractive_compress(
                            src, question=question, max_chars=max_chars
                        )

                    routed = route_document(
                        text=target,
                        question=question,
                        token_budget=room_for_body,
                        count_tokens=estimate,
                        reserved_output=0,
                        compressor=_compress,
                    )
                    if routed.mode == "verbatim_exceeds_budget" or not routed.model_text:
                        # Verbatim asked but over budget, or empty route: fall back to marked pack.
                        packed = pack_user_message(original, room, estimate)
                        if packed.applied:
                            sent[last_user_idx]["content"] = packed.text
                        document_pack = {
                            "applied": packed.applied,
                            "original_tokens": packed.original_tokens,
                            "kept_tokens": packed.kept_tokens,
                            "chunks_total": packed.chunks_total,
                            "chunks_kept": packed.chunks_kept,
                            "context_route": {
                                "mode": routed.mode,
                                "archive_sha256": routed.archive.sha256,
                                "original_chars": routed.original_chars,
                                "served_chars": packed.kept_tokens if packed.applied else routed.served_chars,
                                "silent_truncation": False,
                                "fallback_reason": routed.fallback_reason
                                or (
                                    "verbatim_exceeds_budget"
                                    if routed.mode == "verbatim_exceeds_budget"
                                    else "empty_route"
                                ),
                                "citations": [
                                    {
                                        "start": c.start,
                                        "end": c.end,
                                        "chunk_id": c.chunk_id,
                                    }
                                    for c in routed.citations
                                ],
                            },
                        }
                    else:
                        wrapper = (
                            f'<document routed="true" mode="{routed.mode}" '
                            f'original_sha256="{routed.archive.sha256}" '
                            f'original_chars="{routed.original_chars}" '
                            f'served_chars="{routed.served_chars}" '
                            f'silent_truncation="false"'
                            + (
                                f' fallback="{routed.fallback_reason}"'
                                if routed.fallback_reason
                                else ""
                            )
                            + f">\n{routed.model_text}\n</document>"
                        )
                        sent[last_user_idx]["content"] = (
                            f"{query}\n\n{wrapper}".strip() if query else wrapper
                        )
                        document_pack = {
                            "applied": True,
                            "original_tokens": routed.original_tokens,
                            "kept_tokens": routed.served_tokens,
                            "chunks_total": max(1, len(routed.citations)),
                            "chunks_kept": max(1, len(routed.citations)),
                            "context_route": {
                                "mode": routed.mode,
                                "archive_sha256": routed.archive.sha256,
                                "original_chars": routed.original_chars,
                                "served_chars": routed.served_chars,
                                "silent_truncation": routed.silent_truncation,
                                "fallback_reason": routed.fallback_reason,
                                "citations": [
                                    {
                                        "start": c.start,
                                        "end": c.end,
                                        "chunk_id": c.chunk_id,
                                    }
                                    for c in routed.citations
                                ],
                            },
                        }

        if fence and last_user_idx is not None:
            sent[last_user_idx]["content"] = (
                fence + "\n\n" + (sent[last_user_idx].get("content") or "")
            )

        prompt_tokens = self.tokenizer.count_messages(sent)
        if full_document and prompt_tokens > budget:
            raise ValueError("full document exceeds practical context budget")
        snapshot = {
            "effective_system_prompt": system_text,
            "sent_messages": sent,
            "truncated": truncated or built.compressed,
            "compressed": built.compressed,
            "history_summary": built.summary,
            "dialogue_state": built.state.__dict__,
            "dropped_message_ids": dropped or built.dropped_ids,
            "memory_ids": [m.id for m in memories],
            "occupancy": {
                "effective_window_tokens": budget,
                "prompt_soft_target": prompt_soft_target or budget,
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
        snapshot["dialogue_state_obj"] = built.state
        snapshot["history_summary"] = built.summary
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
        answer_check: dict[str, Any] | None = None,
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
        if answer_check is not None:
            existing = conn.execute(
                "SELECT metadata_json FROM messages WHERE id=?",
                (assistant_id,),
            ).fetchone()
            meta: dict[str, Any] = {}
            if existing and existing["metadata_json"]:
                try:
                    loaded = json.loads(existing["metadata_json"])
                except json.JSONDecodeError:
                    loaded = {}
                if isinstance(loaded, dict):
                    meta = loaded
            meta["answer_check"] = {
                "original": answer_check.get("original", ""),
                "reason": answer_check.get("reason", ""),
                "applied": bool(answer_check.get("applied")),
            }
            conn.execute(
                "UPDATE messages SET metadata_json=? WHERE id=?",
                (json.dumps(meta, ensure_ascii=False), assistant_id),
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
        continue_generation: bool = False,
        profile: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        min_p: float | None = None,
        presence_penalty: float | None = None,
        presence_context_size: int | None = None,
        frequency_penalty: float | None = None,
        frequency_context_size: int | None = None,
        repetition_penalty: float | None = None,
        repetition_context_size: int | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool | None = None,
        reasoning_effort: str | None = None,
        thinking_continuation: bool | None = None,
        owner_id: str | None = None,
        evidence: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        s = self.settings
        text = (message or "").strip()
        skip_user_insert = False
        resume_assistant = False
        resume_assistant_id = ""
        resume_content = ""
        resume_reasoning = ""
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
        elif continue_generation:
            if not conversation_id:
                yield {
                    "event": "error",
                    "data": {
                        "error": {
                            "message": "conversation_id required to continue",
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
            assistants = [m for m in existing["messages"] if m["role"] == "assistant"]
            if not users or not assistants:
                yield {
                    "event": "error",
                    "data": {
                        "error": {
                            "message": "no incomplete assistant turn to continue",
                            "type": "invalid_request_error",
                            "code": "invalid_body",
                        }
                    },
                    "status": 400,
                }
                return
            text = (users[-1].get("content") or "").strip()
            last_asst = assistants[-1]
            finish = last_asst.get("finish_reason")
            if last_asst.get("status") == "complete" and finish not in {
                "length",
                "completed_length",
            }:
                yield {
                    "event": "error",
                    "data": {
                        "error": {
                            "message": "last assistant turn already completed",
                            "type": "invalid_request_error",
                            "code": "invalid_body",
                        }
                    },
                    "status": 400,
                }
                return
            resume_assistant = True
            resume_assistant_id = last_asst["id"]
            resume_content = last_asst.get("content") or ""
            resume_reasoning = last_asst.get("reasoning") or ""
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
        profile_name = profile or s.default_profile
        preset = resolve_profile(profile_name)
        enable_thinking = (
            preset["enable_thinking"] if enable_thinking is None else enable_thinking
        )
        sampled = resolve_sampling(
            enable_thinking=enable_thinking,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            presence_penalty=presence_penalty,
            presence_context_size=presence_context_size,
            frequency_penalty=frequency_penalty,
            frequency_context_size=frequency_context_size,
            repetition_penalty=repetition_penalty,
            repetition_context_size=repetition_context_size,
            base=THINKING if enable_thinking else preset,
        )
        temperature = sampled["temperature"]
        top_p = sampled["top_p"]
        top_k = sampled["top_k"]
        max_tokens = preset["max_tokens"] if max_tokens is None else max_tokens
        if max_tokens is None:
            max_tokens = s.default_max_tokens
        max_tokens = max(1, min(int(max_tokens), s.max_tokens_cap))
        effort = normalize_effort(reasoning_effort or preset.get("reasoning_effort") or s.reasoning_effort)
        use_think_cut = (
            s.thinking_continuation
            if thinking_continuation is None
            else thinking_continuation
        )
        system_prompt = (system if system is not None else s.default_system) or ""
        params = {
            "profile": preset["profile"],
            **sampled,
            "max_tokens": max_tokens,
            "enable_thinking": enable_thinking,
            "reasoning_effort": effort,
            "thinking_continuation": bool(use_think_cut and enable_thinking),
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

        conflict = None
        async with self._lock:
            if cid in self._busy:
                conflict = "generation already in progress"
            elif len(self._busy) >= s.generation_concurrency:
                conflict = "model is busy"
            else:
                self._busy.add(cid)
        if conflict:
            yield {
                "event": "error",
                "data": {
                    "error": {
                        "message": conflict,
                        "type": "invalid_request_error",
                        "code": "generation_in_progress",
                    }
                },
                "status": 409,
            }
            return

        started = now_ms()
        user_id = ""
        assistant_id = ""
        snapshot_id = ""
        content_buf = resume_content
        answer_check: dict[str, Any] | None = None
        reasoning_buf = resume_reasoning
        prompt_tokens = 0
        completion_tokens = 0
        cached_tokens = 0
        usage_source = "estimated"
        status = "complete"
        error = None
        occupancy: dict[str, Any] = {}
        ledger = StreamLedger(started_ms=started)
        terminal = TerminalState.UNKNOWN_TERMINAL
        finish = None
        snapshot_meta: dict[str, Any] = {}

        continue_tail = ""

        def make_req(messages: list[dict[str, Any]], max_out: int) -> ChatRequest:
            nonlocal continue_tail
            extra: dict[str, Any] = {
                "used_continue_prompts": self._used_continue_prompts(cid),
            }
            if resume_assistant and (resume_content or resume_reasoning):
                if resume_content:
                    asst = continue_assistant_message(resume_content, resume_reasoning)
                    prompt, continue_tail = self.tokenizer.continuation_completion_prompt(
                        [*messages, asst],
                        enable_thinking=enable_thinking,
                        used_prompts=extra["used_continue_prompts"],
                    )
                else:
                    prompt, continue_tail = self.tokenizer.mid_think_completion_prompt(
                        messages,
                        resume_reasoning,
                        used_prompts=extra["used_continue_prompts"],
                    )
                extra["raw_prompt"] = prompt
                extra["continue_dropped_tail"] = continue_tail
            return ChatRequest(
                messages=messages,
                temperature=sampled["temperature"],
                top_p=sampled["top_p"],
                top_k=sampled["top_k"],
                min_p=sampled["min_p"],
                presence_penalty=sampled["presence_penalty"],
                presence_context_size=sampled["presence_context_size"],
                frequency_penalty=sampled["frequency_penalty"],
                frequency_context_size=sampled["frequency_context_size"],
                repetition_penalty=sampled["repetition_penalty"],
                repetition_context_size=sampled["repetition_context_size"],
                max_tokens=max_out,
                enable_thinking=enable_thinking,
                reasoning_effort=effort,
                preserve_thinking=s.preserve_thinking,
                extra=extra,
            )

        think_cut = False
        think_budget = None
        think_max = 0
        tail_stripper = TailStripper("")

        async def consume_stream(agen):
            nonlocal content_buf, reasoning_buf, prompt_tokens, completion_tokens, cached_tokens, usage_source, think_cut
            try:
                async for chunk in agen:
                    if chunk.wire_done:
                        ledger.observe_done_wire()
                        continue
                    if chunk.malformed:
                        ledger.malformed_frames += 1
                        continue
                    if chunk.http_eof:
                        ledger.http_eof = True
                        continue
                    if chunk.keepalive:
                        yield {"event": "ping", "data": {"keepalive": chunk.keepalive}}
                        continue
                    now = now_ms()
                    if chunk.delta_reasoning:
                        reasoning_buf += chunk.delta_reasoning
                        ledger.had_output = True
                        if ledger.first_any_ms is None:
                            ledger.first_any_ms = now
                        yield {"event": "delta", "data": {"reasoning": chunk.delta_reasoning}}
                        if (
                            use_think_cut
                            and enable_thinking
                            and think_budget
                            and not content_buf
                            and self.tokenizer.count_text(reasoning_buf) >= think_max
                        ):
                            think_cut = True
                            break
                    if chunk.delta_content:
                        visible = tail_stripper.feed(chunk.delta_content)
                        if visible:
                            content_buf += visible
                            ledger.had_output = True
                            if ledger.first_any_ms is None:
                                ledger.first_any_ms = now
                            if ledger.first_visible_ms is None:
                                ledger.first_visible_ms = now
                            yield {"event": "delta", "data": {"content": visible}}
                            if hard_self_loop(content_buf):
                                ledger.repetition_guard = True
                                break
                    if chunk.finish_reason:
                        ledger.observe_finish(chunk.finish_reason)
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

        try:
            if skip_user_insert:
                hist = self._load_history(cid)
                last_u = next((m for m in reversed(hist) if m.get("role") == "user"), None)
                user_id = (last_u or {}).get("id") or ""
            else:
                user_id, _ = self._insert_message(cid, "user", text)
            if resume_assistant and resume_assistant_id:
                assistant_id = resume_assistant_id
                self._conn().execute(
                    "UPDATE messages SET status='streaming', updated_at=? WHERE id=?",
                    (now_ms(), assistant_id),
                )
                self._conn().commit()
                history = [m for m in self._load_history(cid) if m["id"] != assistant_id]
            else:
                assistant_id, _ = self._insert_message(
                    cid, "assistant", "", status="streaming"
                )
                history = [m for m in self._load_history(cid) if m["id"] != assistant_id]
            prior_state, prior_summary = self._load_dialogue_meta(cid)
            sent, snapshot_meta = self._build_payload(
                history,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
                reasoning_effort=effort,
                conversation_id=cid,
                owner_id=owner_id,
                prior_state=prior_state,
                prior_summary=prior_summary,
                prompt_budget=preset.get("prompt_budget"),
                prompt_soft_target=preset.get("prompt_soft_target"),
            )
            occupancy = snapshot_meta["occupancy"]
            prompt_tokens = occupancy["prompt_tokens"]
            if (
                occupancy["prompt_tokens"] + max_tokens > s.context_window
                and s.overflow_policy == "error"
            ):
                status = "error"
                error = "prompt exceeds practical context budget"
                ledger.exception = RuntimeError(error)
                return

            snapshot_id = self._save_snapshot(cid, snapshot_meta, params)
            if not resume_assistant:
                self._clear_continue_prompts(cid)
            self._save_dialogue_meta(
                cid,
                state=snapshot_meta.get("dialogue_state_obj") or DialogueState(),
                summary=snapshot_meta.get("history_summary"),
                params=params,
            )
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
                    "history_summary": snapshot_meta.get("history_summary"),
                    "dialogue_state": snapshot_meta.get("dialogue_state"),
                    "truncation": {
                        "applied": snapshot_meta["truncated"],
                        "policy": "fold_turns" if snapshot_meta["truncated"] else "none",
                        "dropped_message_ids": snapshot_meta["dropped_message_ids"],
                    },
                },
            }

            think_budget = thinking_budget_for(
                effort,
                low=s.thinking_budget_low,
                medium=s.thinking_budget_medium,
                xhigh=s.thinking_budget_xhigh,
            )
            think_max, leftover_min = thinking_token_split(max_tokens, think_budget)
            req = make_req(sent, max_tokens)
            tail_stripper = TailStripper(continue_tail)

            if not stream:
                first_max = max_tokens
                if use_think_cut and think_budget and enable_thinking:
                    first_max = think_max
                first_req = make_req(sent, first_max)
                if (first_req.extra or {}).get("raw_prompt"):
                    self._remember_continue_prompt(cid, first_req.extra["raw_prompt"])
                result = await self.provider.complete(first_req)
                extra_content = result.content or ""
                if resume_assistant:
                    extra_content = strip_regenerated_tail(extra_content, continue_tail)
                content_buf = (resume_content + extra_content) if resume_assistant else extra_content
                extra_reason = result.reasoning or ""
                reasoning_buf = (
                    (resume_reasoning + extra_reason) if resume_assistant and extra_reason else (extra_reason or resume_reasoning)
                )
                if not reasoning_buf and content_buf:
                    content_buf, reasoning_buf = split_thinking(content_buf)
                if (
                    use_think_cut
                    and think_budget
                    and enable_thinking
                    and not result.content
                    and hasattr(self.provider, "complete_after_think")
                ):
                    leftover = max(leftover_min, max_tokens - self.tokenizer.count_text(reasoning_buf))
                    extra = await self.provider.complete_after_think(
                        first_req, reasoning_buf, leftover
                    )
                    think_prompt = (first_req.extra or {}).get("raw_prompt") or ""
                    if think_prompt:
                        self._remember_continue_prompt(cid, think_prompt)
                    extra_visible = extra.content or ""
                    if resume_assistant:
                        extra_visible = strip_regenerated_tail(extra_visible, continue_tail)
                    content_buf = (resume_content + extra_visible) if resume_assistant else extra_visible
                    result = extra
                ledger.observe_finish(result.finish_reason)
                ledger.observe_done_wire()
                ledger.had_output = bool(content_buf or reasoning_buf)
                if result.prompt_tokens is not None:
                    prompt_tokens = result.prompt_tokens
                    usage_source = result.usage_source
                if result.completion_tokens:
                    completion_tokens = result.completion_tokens
                cached_tokens = result.cached_tokens
                if content_buf:
                    yield {"event": "delta", "data": {"content": content_buf}}
                if reasoning_buf:
                    yield {"event": "delta", "data": {"reasoning": reasoning_buf}}
            else:
                if (req.extra or {}).get("raw_prompt"):
                    self._remember_continue_prompt(cid, req.extra["raw_prompt"])
                async for event in consume_stream(self.provider.stream(req)):
                    yield event
                if (
                    think_cut
                    and not content_buf
                    and hasattr(self.provider, "stream_after_think")
                ):
                    leftover = max(leftover_min, max_tokens - self.tokenizer.count_text(reasoning_buf))
                    async for event in consume_stream(
                        self.provider.stream_after_think(req, reasoning_buf, leftover)
                    ):
                        yield event
                    think_prompt = (req.extra or {}).get("raw_prompt") or ""
                    if think_prompt:
                        self._remember_continue_prompt(cid, think_prompt)
                if not reasoning_buf and content_buf:
                    visible, hidden = split_thinking(content_buf)
                    if hidden:
                        content_buf, reasoning_buf = visible, hidden
            if not completion_tokens:
                completion_tokens = self.tokenizer.count_text(
                    (reasoning_buf or "") + (content_buf or "")
                )
            ledger.thinking_tokens = self.tokenizer.count_text(reasoning_buf or "")
            ledger.visible_tokens = self.tokenizer.count_text(content_buf or "")
            if not stream and not ledger.http_eof and not ledger.saw_done_wire:
                ledger.http_eof = True
        except (asyncio.CancelledError, GeneratorExit):
            ledger.cancelled = True
            status = "cancelled"
            error = "cancelled"
            raise
        except TimeoutError as exc:
            ledger.exception = exc
            error = str(exc)
            self.note_inference_timeout(error)
        except ConnectionError as exc:
            ledger.exception = exc
            error = str(exc)
            self.note_inference_timeout(error)
        except Exception as exc:  # noqa: BLE001
            ledger.exception = exc
            error = str(exc)
            if "exceeds practical context" not in error:
                self.note_inference_failure(error)
        finally:
            ledger.ended_ms = now_ms()
            terminal = ledger.classify()
            if terminal in COMPLETE_STATES:
                self.note_inference_success()
            elif (
                resume_assistant
                and ledger.exception is None
                and terminal is TerminalState.INTERRUPTED_TRANSPORT
                and not ledger.had_output
            ):
                self.note_inference_timeout(
                    "continue completions ended without a terminal"
                )
            status = ledger.message_status(terminal)
            finish = ledger.stored_finish_reason(terminal)
            if terminal is TerminalState.INTERRUPTED_TRANSPORT and not error:
                error = "upstream stream ended before a reliable terminal"
            if evidence and content_buf:
                checked = verify_answer(
                    question=text,
                    evidence=evidence,
                    model_output=content_buf,
                )
                answer_check = {
                    "original": content_buf,
                    "reason": checked.source,
                    "applied": False,
                }
                reliable = checked.source in {
                    "evidence",
                    "evidence_difference",
                    "evidence_quote",
                }
                should_apply = reliable and bool(checked.answer) and (
                    checked.model_number_ok is False
                    or checked.unit_restored
                    or checked.extra_context
                )
                if should_apply:
                    content_buf = checked.answer
                    answer_check["applied"] = True
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
                        status=status,
                        finish_reason=finish,
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
                        answer_check=answer_check,
                    )
            finally:
                self._busy.discard(cid)

        hard_fail = (
            error
            and status == "error"
            and not content_buf
            and not reasoning_buf
            and terminal
            in {
                TerminalState.GENERATION_ERROR,
                TerminalState.TIMEOUT,
                TerminalState.INTERRUPTED_TRANSPORT,
            }
        )
        if hard_fail:
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

        metrics = ledger.to_metrics(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
        )
        usage = {
            "input": prompt_tokens,
            "output": completion_tokens,
            "total": prompt_tokens + completion_tokens,
            "cached": cached_tokens,
            "source": usage_source,
            "ttft_ms": metrics["ttft_ms"],
            "total_latency_ms": metrics["total_latency_ms"],
            "effective_output_tokens_per_sec": metrics["effective_output_tokens_per_sec"],
            "decode_tokens_per_sec": metrics["decode_tokens_per_sec"],
        }
        yield {"event": "usage", "data": usage}
        yield {
            "event": "done",
            "data": {
                "finish_reason": finish,
                "model_finish_reason": ledger.model_finish_reason,
                "transport_integrity": ledger.transport_integrity,
                "terminal_state": terminal.value,
                "incomplete": ledger.incomplete(terminal),
                "metrics": metrics,
                "length_trace": {
                    "requested_max_tokens": max_tokens,
                    "effective_max_tokens": max_tokens,
                    "generated_tokens": completion_tokens,
                    "visible_char_count": len("".join((content_buf or "").split())),
                    "finish_reason": finish,
                    "terminal_state": terminal.value,
                    "model_finish_reason": ledger.model_finish_reason,
                },
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "prompt_tokens_source": usage_source,
                    "cached_tokens": cached_tokens,
                },
                "message": {
                    "id": assistant_id,
                    "role": "assistant",
                    "content": content_buf,
                    "reasoning_content": reasoning_buf or None,
                    "status": status,
                    **({"answer_check": answer_check} if answer_check else {}),
                },
            },
        }
