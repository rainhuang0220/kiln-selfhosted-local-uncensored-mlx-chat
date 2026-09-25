"""Multi-segment narrative orchestrator: one logical assistant message."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.providers.base import ChatRequest
from app.services import narrative_store as store
from app.services.narrative_chars import count_han, count_visible_chars
from app.services.narrative_continuity import check_segment
from app.services.narrative_prompt import build_segment_messages
from app.services.narrative_schema import (
    OutlinePlan,
    SceneState,
    StoryBible,
    build_outline,
    extract_story_bible_from_text,
    sha256_text,
)
from app.services.stream_protocol import StreamLedger, TerminalState


DEFAULT_TARGET_CHARS = 20000
DEFAULT_SEGMENT_CHARS = 2500
DEFAULT_SEGMENT_MAX_TOKENS = 2048


def _patch_assistant(
    chat: Any,
    assistant_id: str,
    *,
    content: str,
    status: str,
    finish_reason: str | None = None,
    completion_tokens: int | None = None,
    error: str | None = None,
) -> None:
    ts = int(time.time() * 1000)
    conn = chat._conn()
    conn.execute(
        """
        UPDATE messages SET
          content=?, status=?, finish_reason=COALESCE(?, finish_reason),
          error=?, completion_tokens=COALESCE(?, completion_tokens),
          updated_at=?
        WHERE id=?
        """,
        (content, status, finish_reason, error, completion_tokens, ts, assistant_id),
    )
    conn.commit()


class NarrativeOrchestrator:
    def __init__(self, chat_service: Any):
        self.chat = chat_service

    async def run(
        self,
        *,
        message: str,
        conversation_id: str | None = None,
        owner_id: str | None = None,
        target_visible_chars: int = DEFAULT_TARGET_CHARS,
        segment_chars: int = DEFAULT_SEGMENT_CHARS,
        segment_max_tokens: int = DEFAULT_SEGMENT_MAX_TOKENS,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        system: str | None = None,
        natural_language_prompt: bool = False,
        cancel_check: Any | None = None,
        resource_check: bool = True,
        min_free_mib: float = 256.0,
    ) -> AsyncIterator[dict[str, Any]]:
        from app.services.narrative_resources import should_pause_for_resources

        s = self.chat.settings
        text = (message or "").strip()
        if not text:
            yield {
                "event": "error",
                "data": {
                    "error": {
                        "message": "empty message",
                        "type": "invalid_request_error",
                        "code": "empty_message",
                    }
                },
                "status": 400,
            }
            return

        target = max(1000, min(int(target_visible_chars), 100_000))
        seg_chars = max(500, min(int(segment_chars), 8000))
        seg_tokens = max(256, min(int(segment_max_tokens), s.max_tokens_cap))

        created = False
        if conversation_id:
            existing = self.chat.get_conversation(conversation_id, owner_id=owner_id)
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
            params = {
                "profile": "long_form",
                "mode": "narrative",
                "target_visible_chars": target,
                "segment_max_tokens": seg_tokens,
            }
            cid = self.chat._create_conversation(
                system or s.default_system or "",
                s.model_name,
                json.dumps(params),
                owner_id=owner_id,
            )
            created = True

        async with self.chat._lock:
            if cid in self.chat._busy:
                yield {
                    "event": "error",
                    "data": {
                        "error": {
                            "message": "generation already in progress",
                            "type": "conflict_error",
                            "code": "generation_busy",
                        }
                    },
                    "status": 409,
                }
                return
            self.chat._busy.add(cid)

        try:
            user_id, _ = self.chat._insert_message(cid, "user", text)
            assistant_id, _ = self.chat._insert_message(
                cid, "assistant", "", status="streaming"
            )

            bible = extract_story_bible_from_text(text)
            if system:
                bible.style = (bible.style or "") + ("; " if bible.style else "") + "custom_system"
            plan = build_outline(
                target_visible_chars=target,
                segment_chars=seg_chars,
                topic=text[:40],
            )
            scene = SceneState(
                time_place="未指定",
                present_characters=[c.name for c in bible.characters[:6]],
                scene_goal=plan.beats[0].goal if plan.beats else "",
                forbidden=list(bible.boundaries),
            )

            job = store.create_job(
                owner_id=owner_id,
                conversation_id=cid,
                assistant_message_id=assistant_id,
                mode="narrative",
                target_visible_chars=target,
                model=s.model_name,
                input_text=text,
                bible_json=bible.to_dict(),
                plan_json=plan.to_dict(),
                scene_json=scene.to_dict(),
                user_authored_config_hash=bible.config_hash(),
            )
            job_id = job["job_id"]

            seq = store.next_event_seq(job_id)
            start_payload = {
                "job_id": job_id,
                "conversation_id": cid,
                "created": created,
                "model": s.model_name,
                "assistant_message_id": assistant_id,
                "message_id": assistant_id,
                "user_message_id": user_id,
                "mode": "narrative",
                "target_visible_chars": target,
                "segment_max_tokens": seg_tokens,
                "plan": plan.to_dict(),
                "length_trace": {
                    "requested_max_tokens": seg_tokens,
                    "effective_max_tokens": seg_tokens,
                    "target_visible_chars": target,
                },
            }
            store.append_event(
                job_id=job_id,
                seq=seq,
                event_type="job_started",
                payload=start_payload,
            )
            yield {"event": "meta", "data": start_payload}

            body = ""
            total_tokens = 0
            ttft_ms = None
            started = int(time.time() * 1000)
            aborted = False
            failed = False
            fail_reason = ""
            beat_queue = list(plan.beats)
            extra_beat_i = 0
            max_extra = 12

            resource_paused = False
            pause_reason = ""
            pause_resources: dict[str, Any] | None = None

            while beat_queue or (
                count_visible_chars(body) < target and extra_beat_i < max_extra and not aborted and not failed and not resource_paused
            ):
                if cancel_check and cancel_check():
                    aborted = True
                    break
                if count_visible_chars(body) >= target:
                    break
                if resource_check:
                    decision = should_pause_for_resources(min_free_mib=min_free_mib)
                    if decision.should_pause:
                        resource_paused = True
                        pause_reason = decision.reason or "resource_pressure"
                        pause_resources = {
                            "swap_free_mib": decision.snapshot.swap_free_mib if decision.snapshot else None,
                            "pages_free": decision.snapshot.pages_free if decision.snapshot else None,
                        }
                        store.update_job_status(
                            job_id,
                            "paused_resource",
                            pause_reason=pause_reason,
                            interrupt_kind="resource_pause",
                        )
                        break
                if beat_queue:
                    beat = beat_queue.pop(0)
                else:
                    # Extend plan until visible target is met (segment EOS != job done).
                    extra_beat_i += 1
                    remain = target - count_visible_chars(body)
                    from app.services.narrative_schema import Beat
                    from app.db import get_conn

                    next_ord = (plan.beats[-1].ordinal + 1) if plan.beats else 0
                    beat = Beat(
                        beat_id=f"beat-extra-{extra_beat_i:03d}",
                        goal=f"续写推进：再完成约 {remain} 可见字符，不要结束整篇。",
                        target_chars=min(seg_chars, max(500, remain)),
                        ordinal=next_ord,
                    )
                    plan.beats.append(beat)
                    get_conn().execute(
                        "UPDATE narrative_jobs SET plan_json=?, updated_at=? WHERE job_id=?",
                        (
                            json.dumps(plan.to_dict(), ensure_ascii=False),
                            int(time.time() * 1000),
                            job_id,
                        ),
                    )
                    get_conn().commit()

                messages = build_segment_messages(
                    bible=bible,
                    plan=plan,
                    beat=beat,
                    scene=scene,
                    retrieved="",
                    continuation_anchor=body,
                    user_brief=text if beat.ordinal == 0 else "",
                    natural_language=natural_language_prompt,
                )
                req = ChatRequest(
                    messages=messages,
                    temperature=0.7 if temperature is None else temperature,
                    top_p=0.9 if top_p is None else top_p,
                    top_k=20 if top_k is None else top_k,
                    max_tokens=seg_tokens,
                    enable_thinking=False,
                    extra={},
                )

                seg_buf = ""
                segment_start = len(body)
                ledger = StreamLedger(started_ms=int(time.time() * 1000))
                prompt_tokens = 0
                completion_tokens = 0
                cached_tokens = 0

                seq = store.next_event_seq(job_id)
                store.append_event(
                    job_id=job_id,
                    seq=seq,
                    event_type="segment_started",
                    payload={
                        "job_id": job_id,
                        "segment_ordinal": beat.ordinal,
                        "beat_id": beat.beat_id,
                        "seq": seq,
                    },
                    content_offset=segment_start,
                )
                yield {
                    "event": "narrative_segment",
                    "data": {
                        "job_id": job_id,
                        "phase": "start",
                        "beat_id": beat.beat_id,
                        "ordinal": beat.ordinal,
                        "seq": seq,
                        "target_chars": beat.target_chars,
                    },
                }

                try:
                    agen = self.chat.provider.stream(req)
                    async for chunk in agen:
                        if cancel_check and cancel_check():
                            aborted = True
                            break
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
                        now = int(time.time() * 1000)
                        if chunk.delta_content:
                            seg_buf += chunk.delta_content
                            body += chunk.delta_content
                            ledger.had_output = True
                            if ledger.first_visible_ms is None:
                                ledger.first_visible_ms = now
                                if ttft_ms is None:
                                    ttft_ms = now - started
                            _patch_assistant(
                                self.chat,
                                assistant_id,
                                content=body,
                                status="streaming",
                            )
                            seq = store.next_event_seq(job_id)
                            store.append_event(
                                job_id=job_id,
                                seq=seq,
                                event_type="delta",
                                payload={
                                    "job_id": job_id,
                                    "seq": seq,
                                    "content": chunk.delta_content,
                                    "offset": len(body) - len(chunk.delta_content),
                                },
                                content_offset=len(body) - len(chunk.delta_content),
                            )
                            yield {
                                "event": "delta",
                                "data": {
                                    "content": chunk.delta_content,
                                    "job_id": job_id,
                                    "seq": seq,
                                    "offset": len(body) - len(chunk.delta_content),
                                },
                            }
                        if chunk.finish_reason:
                            ledger.observe_finish(chunk.finish_reason)
                        if chunk.prompt_tokens is not None:
                            prompt_tokens = chunk.prompt_tokens
                        if chunk.completion_tokens is not None:
                            completion_tokens = chunk.completion_tokens
                        if chunk.cached_tokens is not None:
                            cached_tokens = chunk.cached_tokens
                    closer = getattr(agen, "aclose", None)
                    if closer is not None:
                        await closer()
                except Exception as exc:  # noqa: BLE001 - surface to job status
                    failed = True
                    fail_reason = f"{type(exc).__name__}: {exc}"
                    break

                if aborted:
                    break

                report = check_segment(
                    seg_buf,
                    prior_text=body[:segment_start],
                    min_chars=min(80, beat.target_chars // 4),
                )
                # Soft gate: keep segment but record failures for eval.
                state_before = scene.to_dict()
                scene.open_events = (scene.open_events + [f"完成{beat.beat_id}"])[-12:]
                scene.version += 1
                state_after = scene.to_dict()
                idem = f"{job_id}:{beat.beat_id}:{sha256_text(seg_buf)[:16]}"
                committed = store.commit_segment(
                    job_id=job_id,
                    ordinal=beat.ordinal,
                    beat_id=beat.beat_id,
                    content=seg_buf,
                    start_offset=segment_start,
                    generated_token_count=completion_tokens or 0,
                    finish_reason=ledger.finish_reason or "stop",
                    state_before=state_before,
                    state_after=state_after,
                    idempotency_key=idem,
                    transport_integrity="ok" if ledger.malformed_frames == 0 else "degraded",
                )
                total_tokens += completion_tokens or 0
                store.update_job_status(
                    job_id,
                    "running",
                    next_beat_id=None,
                    scene_json=scene.to_dict(),
                )
                seq = store.next_event_seq(job_id)
                seg_end = {
                    "job_id": job_id,
                    "seq": seq,
                    "segment_id": committed["segment_id"],
                    "beat_id": beat.beat_id,
                    "ordinal": beat.ordinal,
                    "finish_reason": committed["finish_reason"],
                    "visible_chars": committed["visible_chars"],
                    "han_chars": committed["han_chars"],
                    "total_visible_chars": count_visible_chars(body),
                    "continuity": {
                        "ok": report.ok,
                        "reasons": report.reasons,
                        "repeat_ratio": report.repeat_ratio,
                    },
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "cached_tokens": cached_tokens,
                    },
                    "output_sha256": committed["output_sha256"],
                }
                store.append_event(
                    job_id=job_id,
                    seq=seq,
                    event_type="segment_end",
                    payload=seg_end,
                    content_offset=len(body),
                    content_sha256=committed["output_sha256"],
                )
                yield {"event": "narrative_segment", "data": {**seg_end, "phase": "end"}}

                # Segment finish_reason=length means continue next beat, not job done.
                if count_visible_chars(body) >= target:
                    break

            visible = count_visible_chars(body)
            han = count_han(body)
            ended = int(time.time() * 1000)
            if failed:
                status = "error"
                terminal = TerminalState.GENERATION_ERROR.value
                finish = "error"
                store.update_job_status(job_id, "failed")
                _patch_assistant(
                    self.chat,
                    assistant_id,
                    content=body,
                    status="error",
                    error=fail_reason,
                    finish_reason="error",
                )
            elif resource_paused:
                status = "complete"
                terminal = "paused_resource"
                finish = "resource_pause"
                # Job status already set to paused_resource before break.
                _patch_assistant(
                    self.chat,
                    assistant_id,
                    content=body,
                    status="complete",
                    finish_reason="resource_pause",
                    completion_tokens=total_tokens,
                )
            elif aborted:
                status = "cancelled"
                terminal = TerminalState.INTERRUPTED_USER.value
                finish = "abort"
                store.update_job_status(job_id, "aborted")
                _patch_assistant(
                    self.chat,
                    assistant_id,
                    content=body,
                    status="cancelled",
                    finish_reason="abort",
                )
            elif visible >= target:
                status = "complete"
                terminal = TerminalState.COMPLETED_STOP.value
                finish = "stop"
                store.update_job_status(job_id, "completed")
                _patch_assistant(
                    self.chat,
                    assistant_id,
                    content=body,
                    status="complete",
                    finish_reason="stop",
                    completion_tokens=total_tokens,
                )
            else:
                # Finished beats early without reaching target — incomplete length.
                status = "complete"
                terminal = TerminalState.COMPLETED_LENGTH.value
                finish = "length"
                store.update_job_status(job_id, "completed_short")
                _patch_assistant(
                    self.chat,
                    assistant_id,
                    content=body,
                    status="complete",
                    finish_reason="length",
                    completion_tokens=total_tokens,
                )

            reassembled = store.reassemble_body(job_id)
            # Prefer live buffer; segments should match.
            final_body = body if body else reassembled
            metrics = {
                "ttft_ms": ttft_ms,
                "total_latency_ms": ended - started,
                "segments": len(store.list_segments(job_id)),
                "visible_char_count": visible,
                "han_count": han,
                "target_visible_chars": target,
                "total_model_tokens": total_tokens,
            }
            done = {
                "finish_reason": finish,
                "terminal_state": terminal,
                "job_id": job_id,
                "mode": "narrative",
                "incomplete": status != "complete" or visible < target or resource_paused,
                "metrics": metrics,
                "length_trace": {
                    "requested_max_tokens": seg_tokens,
                    "effective_max_tokens": seg_tokens,
                    "generated_tokens": total_tokens,
                    "visible_char_count": visible,
                    "han_count": han,
                    "finish_reason": finish,
                    "terminal_state": terminal,
                    "target_visible_chars": target,
                    "body_sha256": sha256_text(final_body),
                    "segments_sha256": sha256_text(reassembled),
                    "committed_only": True,
                },
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": total_tokens,
                    "total_tokens": total_tokens,
                    "cached_tokens": 0,
                },
                "message": {
                    "id": assistant_id,
                    "role": "assistant",
                    "content": final_body,
                    "status": status if status != "complete" else "complete",
                },
                "conversation_id": cid,
            }
            if resource_paused:
                done["pause_reason"] = pause_reason
                done["resources"] = pause_resources
            seq = store.next_event_seq(job_id)
            event_type = (
                "user_aborted"
                if aborted
                else ("backend_failed" if failed else "job_completed")
            )
            store.append_event(
                job_id=job_id,
                seq=seq,
                event_type=event_type,
                payload=done,
                content_offset=len(final_body),
                content_sha256=sha256_text(final_body),
            )
            yield {"event": "usage", "data": metrics}
            yield {"event": "done", "data": done}
        finally:
            async with self.chat._lock:
                self.chat._busy.discard(cid)

    async def continue_job(
        self,
        *,
        job_id: str,
        owner_id: str | None = None,
        assistant_message_id: str | None = None,
        idempotency_key: str,
        segment_max_tokens: int | None = None,
        max_new_segments: int = 8,
        cancel_check: Any | None = None,
        interrupt_kind: str | Any = "network_disconnect",
        resource_check: bool = True,
        min_free_mib: float = 256.0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Resume a persisted narrative job from committed segments only."""
        from app.services.narrative_resources import should_pause_for_resources
        from app.services.narrative_schema import Beat

        def _resolve_interrupt() -> str:
            if callable(interrupt_kind):
                try:
                    return str(interrupt_kind() or "network_disconnect")
                except Exception:  # noqa: BLE001
                    return "network_disconnect"
            return str(interrupt_kind or "network_disconnect")

        job = store.get_job(job_id, owner_id=owner_id)
        if job is None:
            yield {
                "event": "error",
                "data": {
                    "error": {
                        "message": "job not found",
                        "type": "not_found_error",
                        "code": "job_not_found",
                    }
                },
                "status": 404,
            }
            return

        asst_id = assistant_message_id or job["assistant_message_id"]
        if asst_id != job["assistant_message_id"]:
            yield {
                "event": "error",
                "data": {
                    "error": {
                        "message": "assistant_message_id mismatch",
                        "type": "invalid_request_error",
                        "code": "assistant_mismatch",
                    }
                },
                "status": 400,
            }
            return

        # Idempotency wins over local status — replay before any new work.
        cont = store.begin_continue_request(
            job_id=job_id, idempotency_key=idempotency_key, owner_id=owner_id
        )
        if cont.get("status") == "completed" and cont.get("result_json"):
            result = json.loads(cont["result_json"])
            result["idempotent_replay"] = True
            yield {"event": "meta", "data": {"job_id": job_id, "idempotent_replay": True}}
            yield {"event": "done", "data": result}
            return

        if job["status"] == "completed":
            body = store.reassemble_body(job_id)
            done = {
                "finish_reason": "stop",
                "terminal_state": "completed_stop",
                "job_id": job_id,
                "idempotent_replay": False,
                "already_complete": True,
                "message": {"id": asst_id, "role": "assistant", "content": body, "status": "complete"},
                "length_trace": {
                    "visible_char_count": count_visible_chars(body),
                    "han_count": count_han(body),
                    "target_visible_chars": job["target_visible_chars"],
                },
                "conversation_id": job["conversation_id"],
            }
            store.complete_continue_request(cont["request_id"], done)
            yield {"event": "done", "data": done}
            return

        request_id = cont["request_id"]
        cid = job["conversation_id"]
        async with self.chat._lock:
            if cid in self.chat._busy:
                yield {
                    "event": "error",
                    "data": {
                        "error": {
                            "message": "generation already in progress",
                            "type": "conflict_error",
                            "code": "generation_busy",
                        }
                    },
                    "status": 409,
                }
                return
            self.chat._busy.add(cid)

        try:
            # Canonical body = durably committed segments only.
            body = store.sync_message_to_segments(job_id, asst_id)
            target = int(job["target_visible_chars"] or DEFAULT_TARGET_CHARS)
            s = self.chat.settings
            seg_tokens = max(
                256,
                min(int(segment_max_tokens or 640), s.max_tokens_cap),
            )
            bible = StoryBible.from_dict(json.loads(job["bible_json"] or "{}"))
            plan = OutlinePlan.from_dict(json.loads(job["plan_json"] or "{}"))
            scene = SceneState.from_dict(json.loads(job["scene_json"] or "{}"))
            source = store.get_source_doc(job_id)

            store.update_job_status(job_id, "running", pause_reason="", interrupt_kind="")
            seq = store.next_event_seq(job_id)
            meta = {
                "job_id": job_id,
                "conversation_id": cid,
                "assistant_message_id": asst_id,
                "message_id": asst_id,
                "mode": "narrative_continue",
                "idempotency_key": idempotency_key,
                "visible_char_count": count_visible_chars(body),
                "target_visible_chars": target,
                "created": False,
                "model": s.model_name,
            }
            store.append_event(job_id=job_id, seq=seq, event_type="continue_started", payload=meta)
            yield {"event": "meta", "data": meta}

            if count_visible_chars(body) >= target:
                store.update_job_status(job_id, "completed")
                _patch_assistant(self.chat, asst_id, content=body, status="complete", finish_reason="stop")
                done = {
                    "finish_reason": "stop",
                    "terminal_state": "completed_stop",
                    "job_id": job_id,
                    "idempotent_replay": False,
                    "message": {"id": asst_id, "role": "assistant", "content": body, "status": "complete"},
                    "length_trace": {
                        "visible_char_count": count_visible_chars(body),
                        "han_count": count_han(body),
                        "target_visible_chars": target,
                        "body_sha256": sha256_text(body),
                    },
                    "conversation_id": cid,
                }
                store.complete_continue_request(request_id, done)
                yield {"event": "done", "data": done}
                return

            aborted = False
            failed = False
            fail_reason = ""
            finish = "stop"
            terminal = TerminalState.COMPLETED_STOP.value
            segments_added = 0
            started = int(time.time() * 1000)
            ttft_ms = None

            while (
                count_visible_chars(body) < target
                and segments_added < max(1, int(max_new_segments))
                and not aborted
                and not failed
            ):
                if cancel_check and cancel_check():
                    aborted = True
                    ik = _resolve_interrupt()
                    finish = "user_stop" if ik == "user_stop" else ik
                    terminal = (
                        TerminalState.INTERRUPTED_USER.value
                        if ik == "user_stop"
                        else "interrupted_transport"
                    )
                    break

                if resource_check:
                    decision = should_pause_for_resources(min_free_mib=min_free_mib)
                    if decision.should_pause:
                        store.update_job_status(
                            job_id,
                            "paused_resource",
                            pause_reason=decision.reason or "resource_pressure",
                            interrupt_kind="resource_pause",
                        )
                        finish = "resource_pause"
                        terminal = "paused_resource"
                        done = {
                            "finish_reason": finish,
                            "terminal_state": terminal,
                            "job_id": job_id,
                            "pause_reason": decision.reason,
                            "resources": {
                                "swap_free_mib": decision.snapshot.swap_free_mib if decision.snapshot else None,
                                "pages_free": decision.snapshot.pages_free if decision.snapshot else None,
                            },
                            "message": {
                                "id": asst_id,
                                "role": "assistant",
                                "content": body,
                                "status": "complete",
                            },
                            "length_trace": {
                                "visible_char_count": count_visible_chars(body),
                                "han_count": count_han(body),
                                "target_visible_chars": target,
                                "body_sha256": sha256_text(body),
                                "committed_only": True,
                            },
                            "conversation_id": cid,
                            "idempotent_replay": False,
                        }
                        _patch_assistant(
                            self.chat, asst_id, content=body, status="complete", finish_reason="length"
                        )
                        store.complete_continue_request(request_id, done)
                        yield {"event": "done", "data": done}
                        return

                remain = target - count_visible_chars(body)
                ordinal = len(store.list_segments(job_id))
                beat = Beat(
                    beat_id=f"beat-continue-{ordinal + 1:03d}",
                    goal=f"续写推进：再完成约 {remain} 可见字符，不要结束整篇。",
                    target_chars=min(2500, max(400, remain)),
                    ordinal=ordinal,
                )
                messages = build_segment_messages(
                    bible=bible,
                    plan=plan,
                    beat=beat,
                    scene=scene,
                    retrieved="",
                    continuation_anchor=body,
                    user_brief=source[:4000] if ordinal == 0 and not body else "",
                )
                req = ChatRequest(
                    messages=messages,
                    temperature=0.7,
                    top_p=0.9,
                    top_k=20,
                    max_tokens=seg_tokens,
                    enable_thinking=False,
                    extra={},
                )

                seg_buf = ""
                segment_start = len(body)
                completion_tokens = 0
                ledger = StreamLedger(started_ms=int(time.time() * 1000))
                seq = store.next_event_seq(job_id)
                store.append_event(
                    job_id=job_id,
                    seq=seq,
                    event_type="segment_started",
                    payload={"job_id": job_id, "beat_id": beat.beat_id, "ordinal": ordinal},
                    content_offset=segment_start,
                )
                yield {
                    "event": "narrative_segment",
                    "data": {
                        "job_id": job_id,
                        "phase": "start",
                        "beat_id": beat.beat_id,
                        "ordinal": ordinal,
                        "seq": seq,
                    },
                }

                try:
                    agen = self.chat.provider.stream(req)
                    async for chunk in agen:
                        if cancel_check and cancel_check():
                            aborted = True
                            finish = (
                                "user_stop" if interrupt_kind == "user_stop" else interrupt_kind
                            )
                            terminal = (
                                TerminalState.INTERRUPTED_USER.value
                                if interrupt_kind == "user_stop"
                                else "interrupted_transport"
                            )
                            break
                        if chunk.wire_done:
                            ledger.observe_done_wire()
                            continue
                        if chunk.malformed:
                            ledger.malformed_frames += 1
                            continue
                        if chunk.keepalive:
                            yield {"event": "ping", "data": {"keepalive": chunk.keepalive}}
                            continue
                        now = int(time.time() * 1000)
                        if chunk.delta_content:
                            # Buffer only — do not mutate committed body until save succeeds.
                            seg_buf += chunk.delta_content
                            if ttft_ms is None:
                                ttft_ms = now - started
                            # Stream provisional text to client without counting as committed.
                            yield {
                                "event": "delta",
                                "data": {
                                    "content": chunk.delta_content,
                                    "job_id": job_id,
                                    "provisional": True,
                                    "offset": segment_start + len(seg_buf) - len(chunk.delta_content),
                                },
                            }
                        if chunk.finish_reason:
                            ledger.observe_finish(chunk.finish_reason)
                        if chunk.completion_tokens is not None:
                            completion_tokens = chunk.completion_tokens
                    closer = getattr(agen, "aclose", None)
                    if closer is not None:
                        await closer()
                except Exception as exc:  # noqa: BLE001
                    failed = True
                    fail_reason = f"{type(exc).__name__}: {exc}"
                    finish = "error"
                    terminal = TerminalState.GENERATION_ERROR.value
                    break

                if aborted:
                    # Discard provisional buffer — only committed segments count.
                    break

                try:
                    committed = store.commit_segment(
                        job_id=job_id,
                        ordinal=ordinal,
                        beat_id=beat.beat_id,
                        content=seg_buf,
                        start_offset=segment_start,
                        generated_token_count=completion_tokens or 0,
                        finish_reason=ledger.finish_reason or "stop",
                        state_before=scene.to_dict(),
                        state_after=scene.to_dict(),
                        idempotency_key=f"{job_id}:{beat.beat_id}:{sha256_text(seg_buf)[:16]}",
                    )
                except Exception as exc:  # noqa: BLE001
                    failed = True
                    fail_reason = f"save_failed: {type(exc).__name__}: {exc}"
                    finish = "save_failed"
                    terminal = TerminalState.GENERATION_ERROR.value
                    store.update_job_status(
                        job_id,
                        "failed",
                        pause_reason="save_failed",
                        interrupt_kind="save_failed",
                    )
                    done = {
                        "finish_reason": finish,
                        "terminal_state": terminal,
                        "job_id": job_id,
                        "error": fail_reason,
                        "message": {
                            "id": asst_id,
                            "role": "assistant",
                            "content": body,
                            "status": "error",
                        },
                        "length_trace": {
                            "visible_char_count": count_visible_chars(body),
                            "han_count": count_han(body),
                            "target_visible_chars": target,
                            "committed_only": True,
                        },
                        "conversation_id": cid,
                        "idempotent_replay": False,
                    }
                    store.complete_continue_request(request_id, done, status="failed")
                    yield {"event": "done", "data": done}
                    return

                body = store.reassemble_body(job_id)
                _patch_assistant(self.chat, asst_id, content=body, status="streaming")
                segments_added += 1
                seq = store.next_event_seq(job_id)
                seg_end = {
                    "job_id": job_id,
                    "phase": "end",
                    "segment_id": committed["segment_id"],
                    "beat_id": beat.beat_id,
                    "ordinal": ordinal,
                    "visible_chars": committed["visible_chars"],
                    "total_visible_chars": count_visible_chars(body),
                    "output_sha256": committed["output_sha256"],
                    "seq": seq,
                }
                store.append_event(
                    job_id=job_id,
                    seq=seq,
                    event_type="segment_end",
                    payload=seg_end,
                    content_offset=len(body),
                    content_sha256=committed["output_sha256"],
                )
                yield {"event": "narrative_segment", "data": seg_end}

            visible = count_visible_chars(body)
            han = count_han(body)
            if failed:
                store.update_job_status(
                    job_id, "failed", pause_reason=fail_reason, interrupt_kind="backend_failed"
                )
                _patch_assistant(
                    self.chat, asst_id, content=body, status="error", error=fail_reason, finish_reason="error"
                )
            elif aborted:
                store.update_job_status(
                    job_id,
                    "interrupted_user" if finish == "user_stop" else "interrupted_transport",
                    pause_reason=finish,
                    interrupt_kind=finish,
                )
                _patch_assistant(
                    self.chat, asst_id, content=body, status="cancelled", finish_reason=finish
                )
            elif visible >= target:
                store.update_job_status(job_id, "completed")
                _patch_assistant(
                    self.chat, asst_id, content=body, status="complete", finish_reason="stop"
                )
                finish = "stop"
                terminal = TerminalState.COMPLETED_STOP.value
            else:
                store.update_job_status(
                    job_id, "paused_checkpoint", pause_reason="max_new_segments", interrupt_kind="checkpoint"
                )
                _patch_assistant(
                    self.chat, asst_id, content=body, status="complete", finish_reason="length"
                )
                finish = "length"
                terminal = TerminalState.COMPLETED_LENGTH.value

            done = {
                "finish_reason": finish,
                "terminal_state": terminal,
                "job_id": job_id,
                "idempotent_replay": False,
                "segments_added": segments_added,
                "metrics": {
                    "ttft_ms": ttft_ms,
                    "total_latency_ms": int(time.time() * 1000) - started,
                    "visible_char_count": visible,
                    "han_count": han,
                    "target_visible_chars": target,
                    "segments": len(store.list_segments(job_id)),
                },
                "length_trace": {
                    "visible_char_count": visible,
                    "han_count": han,
                    "target_visible_chars": target,
                    "body_sha256": sha256_text(body),
                    "committed_only": True,
                },
                "message": {
                    "id": asst_id,
                    "role": "assistant",
                    "content": body,
                    "status": "complete" if not failed and not aborted else ("error" if failed else "cancelled"),
                },
                "conversation_id": cid,
            }
            if fail_reason:
                done["error"] = fail_reason
            store.complete_continue_request(
                request_id, done, status="failed" if failed else "completed"
            )
            yield {"event": "usage", "data": done["metrics"]}
            yield {"event": "done", "data": done}
        finally:
            async with self.chat._lock:
                self.chat._busy.discard(cid)


async def resume_events(
    job_id: str,
    *,
    owner_id: str | None,
    last_seq: int = 0,
) -> AsyncIterator[dict[str, Any]]:
    job = store.get_job(job_id, owner_id=owner_id)
    if job is None:
        yield {
            "event": "error",
            "data": {
                "error": {
                    "message": "job not found",
                    "type": "not_found_error",
                    "code": "job_not_found",
                }
            },
            "status": 404,
        }
        return
    for ev in store.events_since(job_id, last_seq):
        et = ev["event_type"]
        if et == "delta":
            yield {"event": "delta", "data": ev["payload"]}
        elif et in {"segment_started", "segment_end"}:
            yield {"event": "narrative_segment", "data": ev["payload"]}
        elif et in {"job_started"}:
            yield {"event": "meta", "data": ev["payload"]}
        elif et in {"job_completed", "user_aborted", "backend_failed"}:
            yield {"event": "done", "data": ev["payload"]}
        else:
            yield {"event": et, "data": ev["payload"]}
