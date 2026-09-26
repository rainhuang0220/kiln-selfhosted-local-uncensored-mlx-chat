"""Character cards for immersive sessions (compiled once into system_prompt)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.db import get_conn
from app.services.literary_system import compile_system


def _now() -> int:
    return int(time.time() * 1000)


def _id() -> str:
    return str(uuid.uuid4())


def _row_to_card(row: Any) -> dict[str, Any]:
    immutable = []
    try:
        immutable = json.loads(row["immutable_json"] or "[]")
    except json.JSONDecodeError:
        immutable = []
    return {
        "id": row["id"],
        "owner_id": row["owner_id"],
        "name": row["name"],
        "description": row["description"] or "",
        "personality": row["personality"] or "",
        "scenario": row["scenario"] or "",
        "speech_style": row["speech_style"] or "",
        "taboos": row["taboos"] or "",
        "relationship_to_user": row["relationship_to_user"] or "",
        "first_mes": row["first_mes"] or "",
        "mes_example": row["mes_example"] or "",
        "immutable_json": immutable,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_cards(owner_id: str | None = None) -> list[dict[str, Any]]:
    conn = get_conn()
    if owner_id:
        rows = conn.execute(
            "SELECT * FROM character_cards WHERE owner_id=? OR owner_id IS NULL ORDER BY updated_at DESC",
            (owner_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM character_cards ORDER BY updated_at DESC"
        ).fetchall()
    return [_row_to_card(r) for r in rows]


def get_card(card_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM character_cards WHERE id=?",
        (card_id,),
    ).fetchone()
    if not row:
        return None
    if owner_id and row["owner_id"] and row["owner_id"] != owner_id:
        return None
    return _row_to_card(row)


def save_card(
    payload: dict[str, Any],
    *,
    owner_id: str | None = None,
    card_id: str | None = None,
) -> dict[str, Any]:
    rid = card_id or payload.get("id") or _id()
    ts = _now()
    immutable = payload.get("immutable_json") or payload.get("immutable") or []
    if isinstance(immutable, str):
        immutable_json = json.dumps([immutable], ensure_ascii=False)
    else:
        immutable_json = json.dumps(list(immutable), ensure_ascii=False)
    name = (payload.get("name") or "").strip() or "未命名角色"
    conn = get_conn()
    existing = conn.execute("SELECT created_at FROM character_cards WHERE id=?", (rid,)).fetchone()
    created = int(existing["created_at"]) if existing else ts
    conn.execute(
        """
        INSERT INTO character_cards (
          id, owner_id, name, description, personality, scenario, speech_style,
          taboos, relationship_to_user, first_mes, mes_example, immutable_json,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          description=excluded.description,
          personality=excluded.personality,
          scenario=excluded.scenario,
          speech_style=excluded.speech_style,
          taboos=excluded.taboos,
          relationship_to_user=excluded.relationship_to_user,
          first_mes=excluded.first_mes,
          mes_example=excluded.mes_example,
          immutable_json=excluded.immutable_json,
          updated_at=excluded.updated_at
        """,
        (
            rid,
            owner_id if owner_id is not None else payload.get("owner_id"),
            name,
            payload.get("description") or "",
            payload.get("personality") or "",
            payload.get("scenario") or "",
            payload.get("speech_style") or "",
            payload.get("taboos") or "",
            payload.get("relationship_to_user") or "",
            payload.get("first_mes") or "",
            payload.get("mes_example") or "",
            immutable_json,
            created,
            ts,
        ),
    )
    conn.commit()
    card = get_card(rid, owner_id=owner_id)
    assert card is not None
    return card


def patch_card(
    card_id: str,
    fields: dict[str, Any],
    *,
    owner_id: str | None = None,
) -> dict[str, Any] | None:
    existing = get_card(card_id, owner_id=owner_id)
    if existing is None:
        return None
    existing.update({k: v for k, v in fields.items() if v is not None})
    return save_card(existing, owner_id=owner_id, card_id=card_id)


def compile_card_system(card: dict[str, Any] | None) -> str:
    return compile_system(card)
