"""SQLite persistence for narrative jobs and segments."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.db import get_conn
from app.services.narrative_chars import count_han, count_visible_chars
from app.services.narrative_schema import sha256_text


def _now() -> int:
    return int(time.time() * 1000)


def create_job(
    *,
    owner_id: str | None,
    conversation_id: str,
    assistant_message_id: str,
    mode: str,
    target_visible_chars: int,
    model: str,
    input_text: str,
    bible_json: dict[str, Any],
    plan_json: dict[str, Any],
    scene_json: dict[str, Any],
    prompt_version: str = "narrative.v1",
    user_authored_config_hash: str = "",
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    now = _now()
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO narrative_jobs(
          job_id, owner_id, conversation_id, assistant_message_id, mode,
          target_visible_chars, status, model, prompt_version,
          user_authored_config_hash, input_sha256, total_visible_chars,
          total_model_tokens, current_segment, next_beat_id, last_event_seq,
          bible_json, plan_json, scene_json, resume_cursor, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            job_id,
            owner_id,
            conversation_id,
            assistant_message_id,
            mode,
            int(target_visible_chars),
            "running",
            model,
            prompt_version,
            user_authored_config_hash,
            sha256_text(input_text),
            0,
            0,
            0,
            None,
            0,
            json.dumps(bible_json, ensure_ascii=False),
            json.dumps(plan_json, ensure_ascii=False),
            json.dumps(scene_json, ensure_ascii=False),
            "",
            now,
            now,
        ),
    )
    # Keep original input archive with offsets for provenance.
    conn.execute(
        """
        INSERT INTO narrative_source_docs(
          doc_id, job_id, owner_id, sha256, content, char_len, created_at
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            job_id,
            owner_id,
            sha256_text(input_text),
            input_text,
            len(input_text),
            now,
        ),
    )
    conn.commit()
    return get_job(job_id, owner_id=owner_id)


def get_job(job_id: str, *, owner_id: str | None = None) -> dict[str, Any] | None:
    conn = get_conn()
    if owner_id is None:
        row = conn.execute("SELECT * FROM narrative_jobs WHERE job_id=?", (job_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM narrative_jobs WHERE job_id=? AND IFNULL(owner_id,'')=IFNULL(?, '')",
            (job_id, owner_id),
        ).fetchone()
    return dict(row) if row else None


def list_segments(job_id: str) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM narrative_segments
        WHERE job_id=?
        ORDER BY ordinal ASC
        """,
        (job_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def next_event_seq(job_id: str) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT last_event_seq FROM narrative_jobs WHERE job_id=?",
        (job_id,),
    ).fetchone()
    seq = int(row["last_event_seq"] if row else 0) + 1
    conn.execute(
        "UPDATE narrative_jobs SET last_event_seq=?, updated_at=? WHERE job_id=?",
        (seq, _now(), job_id),
    )
    conn.commit()
    return seq


def append_event(
    *,
    job_id: str,
    seq: int,
    event_type: str,
    payload: dict[str, Any],
    content_offset: int | None = None,
    content_sha256: str | None = None,
) -> None:
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO narrative_events(
          event_id, job_id, seq, event_type, payload_json,
          content_offset, content_sha256, created_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            job_id,
            seq,
            event_type,
            json.dumps(payload, ensure_ascii=False),
            content_offset,
            content_sha256,
            _now(),
        ),
    )
    conn.commit()


def events_since(job_id: str, last_seq: int = 0) -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM narrative_events
        WHERE job_id=? AND seq>?
        ORDER BY seq ASC
        """,
        (job_id, int(last_seq)),
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        out.append(item)
    return out


def commit_segment(
    *,
    job_id: str,
    ordinal: int,
    beat_id: str,
    content: str,
    start_offset: int,
    generated_token_count: int,
    finish_reason: str,
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    idempotency_key: str,
    transport_integrity: str = "ok",
) -> dict[str, Any]:
    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM narrative_segments WHERE job_id=? AND idempotency_key=?",
        (job_id, idempotency_key),
    ).fetchone()
    if existing:
        return dict(existing)
    end_offset = start_offset + len(content)
    segment_id = str(uuid.uuid4())
    now = _now()
    conn.execute(
        """
        INSERT INTO narrative_segments(
          segment_id, job_id, ordinal, beat_id, start_offset, end_offset,
          generated_token_count, finish_reason, output_sha256, content,
          visible_chars, han_chars, state_before_json, state_after_json,
          durably_committed, transport_integrity, idempotency_key, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)
        """,
        (
            segment_id,
            job_id,
            ordinal,
            beat_id,
            start_offset,
            end_offset,
            int(generated_token_count),
            finish_reason,
            sha256_text(content),
            content,
            count_visible_chars(content),
            count_han(content),
            json.dumps(state_before, ensure_ascii=False),
            json.dumps(state_after, ensure_ascii=False),
            transport_integrity,
            idempotency_key,
            now,
        ),
    )
    job = conn.execute("SELECT * FROM narrative_jobs WHERE job_id=?", (job_id,)).fetchone()
    total_vis = int(job["total_visible_chars"] or 0) + count_visible_chars(content)
    total_tok = int(job["total_model_tokens"] or 0) + int(generated_token_count)
    conn.execute(
        """
        UPDATE narrative_jobs
        SET total_visible_chars=?, total_model_tokens=?, current_segment=?,
            resume_cursor=?, updated_at=?
        WHERE job_id=?
        """,
        (total_vis, total_tok, ordinal + 1, str(end_offset), now, job_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM narrative_segments WHERE segment_id=?",
        (segment_id,),
    ).fetchone()
    return dict(row)


def update_job_status(
    job_id: str,
    status: str,
    *,
    next_beat_id: str | None = None,
    scene_json: dict[str, Any] | None = None,
    pause_reason: str | None = None,
    interrupt_kind: str | None = None,
) -> None:
    conn = get_conn()
    fields = ["status=?", "updated_at=?"]
    args: list[Any] = [status, _now()]
    if next_beat_id is not None:
        fields.append("next_beat_id=?")
        args.append(next_beat_id)
    if scene_json is not None:
        fields.append("scene_json=?")
        args.append(json.dumps(scene_json, ensure_ascii=False))
    if pause_reason is not None:
        fields.append("pause_reason=?")
        args.append(pause_reason)
    if interrupt_kind is not None:
        fields.append("interrupt_kind=?")
        args.append(interrupt_kind)
    args.append(job_id)
    conn.execute(f"UPDATE narrative_jobs SET {', '.join(fields)} WHERE job_id=?", args)
    conn.commit()


def sync_message_to_segments(job_id: str, assistant_message_id: str) -> str:
    """Canonical body is committed segments only; sync message to that body."""
    body = reassemble_body(job_id)
    conn = get_conn()
    conn.execute(
        """
        UPDATE messages SET content=?, updated_at=?
        WHERE id=?
        """,
        (body, _now(), assistant_message_id),
    )
    conn.commit()
    return body


def begin_continue_request(
    *,
    job_id: str,
    idempotency_key: str,
    owner_id: str | None,
) -> dict[str, Any]:
    """Return existing completed request for the same key, or create a new one."""
    conn = get_conn()
    existing = conn.execute(
        """
        SELECT * FROM narrative_continue_requests
        WHERE job_id=? AND idempotency_key=?
        """,
        (job_id, idempotency_key),
    ).fetchone()
    if existing:
        return dict(existing)
    request_id = str(uuid.uuid4())
    now = _now()
    try:
        conn.execute(
            """
            INSERT INTO narrative_continue_requests(
              request_id, job_id, idempotency_key, owner_id, status, result_json, created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (request_id, job_id, idempotency_key, owner_id, "running", None, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        row = conn.execute(
            """
            SELECT * FROM narrative_continue_requests
            WHERE job_id=? AND idempotency_key=?
            """,
            (job_id, idempotency_key),
        ).fetchone()
        if row:
            return dict(row)
        raise
    return dict(
        conn.execute(
            "SELECT * FROM narrative_continue_requests WHERE request_id=?",
            (request_id,),
        ).fetchone()
    )


def complete_continue_request(request_id: str, result: dict[str, Any], *, status: str = "completed") -> None:
    conn = get_conn()
    conn.execute(
        """
        UPDATE narrative_continue_requests
        SET status=?, result_json=?, completed_at=?
        WHERE request_id=?
        """,
        (status, json.dumps(result, ensure_ascii=False), _now(), request_id),
    )
    conn.commit()


def get_source_doc(job_id: str) -> str:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT content FROM narrative_source_docs
        WHERE job_id=?
        ORDER BY created_at ASC LIMIT 1
        """,
        (job_id,),
    ).fetchone()
    return row["content"] if row else ""


def reassemble_body(job_id: str) -> str:
    parts = [s["content"] for s in list_segments(job_id)]
    return "".join(parts)
