from app.services.dialogue_checkpoints import build_immutable_context
from app.services.dialogue_context import build_dialogue_context


def _turns(n: int) -> list[dict]:
    msgs = [{"id": "s", "role": "system", "content": "persona stays put"}]
    for i in range(n):
        msgs.append({"id": f"u{i}", "role": "user", "content": f"user turn {i}。地点：旧书店" if i == 0 else f"user turn {i}"})
        msgs.append({"id": f"a{i}", "role": "assistant", "content": f"assistant turn {i}。钥匙还在。"})
    return msgs


def test_sealed_checkpoint_text_does_not_rewrite_on_next_fold():
    first = build_immutable_context(
        _turns(8),
        budget=10_000,
        estimate=lambda t: max(1, len(t) // 8),
        recent_turn_target=4,
        fold_every_turns=4,
        min_recent_turns=4,
    )
    assert first.checkpoints
    sealed = first.checkpoints[0].text
    second = build_immutable_context(
        _turns(12),
        budget=10_000,
        estimate=lambda t: max(1, len(t) // 8),
        recent_turn_target=4,
        fold_every_turns=4,
        min_recent_turns=4,
    )
    assert second.checkpoints[0].text == sealed
    assert len(second.checkpoints) >= 2
    assert second.checkpoints[1].text != sealed
    first_card = next(m["content"] for m in first.messages if m.get("id") == "checkpoint-0")
    second_card = next(m["content"] for m in second.messages if m.get("id") == "checkpoint-0")
    assert first_card == second_card


def test_compact_rewrites_only_when_chunk_cap_exceeded():
    built = build_immutable_context(
        _turns(20),
        budget=10_000,
        estimate=lambda t: max(1, len(t) // 8),
        recent_turn_target=4,
        fold_every_turns=4,
        min_recent_turns=4,
        max_checkpoints=2,
    )
    assert len(built.checkpoints) <= 2
    assert built.compacted is True


def test_control_keeps_all_turns_when_under_budget():
    built = build_dialogue_context(
        _turns(6),
        budget=50_000,
        estimate=lambda t: 1,
        recent_turn_target=20,
        min_recent_turns=20,
    )
    assert built.compressed is False
    assert not any(m.get("id") == "dialogue-context" for m in built.messages)
