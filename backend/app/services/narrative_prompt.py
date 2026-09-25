"""Layered narrative prompts. Creator notes stay out of the highest-privilege layer."""

from __future__ import annotations

from typing import Any

from app.services.narrative_schema import Beat, OutlinePlan, SceneState, StoryBible


def _join(items: list[str], *, limit: int = 12) -> str:
    cleaned = [x.strip() for x in items if x and str(x).strip()]
    return "；".join(cleaned[:limit]) if cleaned else "（无）"


def build_stable_contract(bible: StoryBible) -> str:
    return (
        f"[STABLE_CONTRACT]\n"
        f"创作模式={bible.mode}; 目标语言=zh-CN; 叙事人称={bible.pov}; "
        f"当前用户的互动控制权={bible.user_agency}; 文风={bible.style or '自然流畅'}; "
        f"角色持续性规则=尊重用户原设、成人角色、不替用户作决定; "
        f"adults_only={bible.adults_only}"
    )


def build_user_canon(bible: StoryBible, *, include_creator_notes: bool = False) -> str:
    chars = []
    for c in bible.characters:
        block = f"{c.name}: {c.description}"
        if c.personality:
            block += f" | 性格={c.personality}"
        if include_creator_notes and c.creator_notes:
            # Explicit opt-in only — never default into stable contract.
            block += f" | notes={c.creator_notes}"
        chars.append(block)
    return (
        f"[USER_AUTHORED_CANON]\n"
        f"用户人设={bible.persona or '（未单独声明）'}; "
        f"主要人物={_join(chars, limit=8)}; "
        f"世界规则={_join(bible.world_rules)}; "
        f"关系与重要历史={_join(bible.relations)}; "
        f"边界={_join(bible.boundaries)}"
    )


def build_job_plan(plan: OutlinePlan, beat: Beat) -> str:
    open_threads = [b.goal for b in plan.beats if b.ordinal > beat.ordinal][:5]
    return (
        f"[JOB_PLAN version={plan.version}]\n"
        f"全局弧线=共{len(plan.beats)}段，目标可见字符={plan.target_visible_chars}; "
        f"当前节拍={beat.beat_id}; 本段目标={beat.goal}; "
        f"未完成伏笔={_join(open_threads, limit=5)}"
    )


def build_scene_snapshot(scene: SceneState) -> str:
    return (
        f"[SCENE_SNAPSHOT version={scene.version}]\n"
        f"时间地点={scene.time_place or '未指定'}; "
        f"当前人物状态={_join(scene.present_characters)}; "
        f"最近已发生事件={_join(scene.open_events)}; "
        f"场景目标={scene.scene_goal or '推进当前节拍'}; "
        f"禁止矛盾={_join(scene.forbidden)}"
    )


def build_segment_messages(
    *,
    bible: StoryBible,
    plan: OutlinePlan,
    beat: Beat,
    scene: SceneState,
    retrieved: str = "",
    continuation_anchor: str = "",
    user_brief: str = "",
    natural_language: bool = False,
) -> list[dict[str, str]]:
    if natural_language:
        system = (
            "你是长篇叙事写作者。只完成当前节拍，不要结束整篇，不要复述已写内容，"
            "不替用户作决定。输出自然连续的中文正文。"
        )
        user = (
            f"设定：{bible.persona}\n人物：{_join([c.name + ':' + c.description for c in bible.characters])}\n"
            f"世界：{_join(bible.world_rules)}\n边界：{_join(bible.boundaries)}\n"
            f"当前场景：{scene.time_place} / {_join(scene.present_characters)}\n"
            f"本段目标：{beat.goal}\n"
            f"相关原文：{retrieved or '（无）'}\n"
            f"续写锚点：{continuation_anchor[-1500:] if continuation_anchor else '（开头）'}\n"
            f"用户请求：{user_brief or '继续写下去'}"
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    system = "\n\n".join(
        [
            build_stable_contract(bible),
            build_user_canon(bible, include_creator_notes=False),
        ]
    )
    user_parts = [
        build_job_plan(plan, beat),
        build_scene_snapshot(scene),
        f"[RELEVANT_SOURCE]\n{retrieved or '（无检索摘录）'}",
        f"[CONTINUATION_ANCHOR]\n{continuation_anchor[-2000:] if continuation_anchor else '（本篇开头）'}",
        (
            "[SEGMENT_REQUEST]\n"
            "只执行当前节拍，保持人物口吻与时间顺序；不要把本段当成整篇完结；"
            "不要复述既有内容；不替用户作决定。输出自然连续的正文，"
            "达到该节拍的叙事目标后在自然段落边界结束。"
        ),
    ]
    if user_brief:
        user_parts.insert(0, f"[USER_BRIEF]\n{user_brief[:8000]}")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def export_config(bible: StoryBible, scene: SceneState | None = None) -> dict[str, Any]:
    return {
        "story_bible": bible.to_dict(),
        "scene_state": (scene or SceneState()).to_dict(),
        "format": "kiln.narrative.v1",
    }


def import_config(payload: dict[str, Any] | None) -> tuple[StoryBible, SceneState]:
    data = dict(payload or {})
    bible = StoryBible.from_dict(data.get("story_bible") or data.get("bible") or data)
    scene = SceneState.from_dict(data.get("scene_state") or data.get("scene") or {})
    return bible, scene
