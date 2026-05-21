"""Tool schemas exposed via ``MemoryProvider.get_tool_schemas`` /
``handle_tool_call``.

Per Hermes contract: handler is sync and returns a JSON string (never raises).

v1.0.0 — Agent Memory v2 tree surface (decisions 660–682, doc-91 §8).
Project tools removed in v0.6.0 (decision-660). The flat v1 memory verbs
(``conport_remember`` / ``conport_recall`` / ``conport_forget`` /
``conport_reflect`` / ``conport_link_memories``) removed in this release
in favour of the 23 ``agent_*`` tools below. ``forget`` and explicit
``link_memories`` have no v2 equivalent — gravity is non-destructive
(decision-667) and tree edges replace ad-hoc links.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .client import ConPortClient


# Trunk sub-store roles surfaced via init payload — used as enum hints for
# ``scope_root_id`` arguments. The actual ids are agent-specific and live
# in ``AgentInitPayload``.
TRUNK_ROOTS = (
    "identity_root_id",
    "principles_root_id",
    "person_knowledge_root_id",
    "trunk_root_id",
)
BRANCH_STATES = ("active", "dormant", "closed")
LIFT_ACTIONS = ("accept", "edit_content", "reject")
PROMOTION_ACTIONS = ("promote", "revert")
SKILL_NOTE_TYPES = ("observation", "correction", "edge_case", "example")


TOOL_SCHEMAS: list[dict[str, Any]] = [
    # ----- writes -----
    {
        "name": "agent_remember",
        "description": (
            "Persist a new memory under the agent's tree. Leave ``parent_id``"
            " null to let the backend route via embedding similarity (the"
            " recommended path — decision-673). Pass an explicit"
            " ``parent_id`` (e.g. an ``identity_root_id``) to anchor the"
            " write inside a specific sub-tree."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "maxLength": 10000},
                "parent_id": {"type": "integer"},
                "branch_id": {"type": "integer"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "agent_recall",
        "description": (
            "Composite-scored search across the agent's memory (decision-678)."
            " score = 0.6·cosine + 0.2·recall_factor + 0.2·foundational_boost."
            " Pass ``scope_root_id`` to narrow to one sub-tree (only person"
            " knowledge, only principles, …) — get the id from"
            " ``agent_init`` output."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "scope_root_id": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "agent_reflect",
        "description": (
            "Manual gravity invoke on a node (decision-667). With"
            " ``new_content`` — persist merged content, refresh embedding,"
            " then run consolidation + skill emergence checks. Without —"
            " pure bookkeeping. Backend never synthesises; you provide"
            " the merge."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {"type": "integer"},
                "new_content": {"type": "string"},
            },
            "required": ["node_id"],
        },
    },
    # ----- tree navigation -----
    {
        "name": "agent_get_node",
        "description": "Fetch one node + immediate children (id + content_preview + branch_id + is_skill).",
        "parameters": {
            "type": "object",
            "properties": {"node_id": {"type": "integer"}},
            "required": ["node_id"],
        },
    },
    {
        "name": "agent_list_branches",
        "description": (
            "List branches optionally filtered by state. Each row is the"
            " branch origin + counters + preview, not the full arc."
        ),
        "parameters": {
            "type": "object",
            "properties": {"state": {"type": "string", "enum": list(BRANCH_STATES)}},
        },
    },
    {
        "name": "agent_walk_branch",
        "description": "Full branch walk: origin + depth-ordered arc + linked artifacts.",
        "parameters": {
            "type": "object",
            "properties": {"branch_id": {"type": "integer"}},
            "required": ["branch_id"],
        },
    },
    # ----- branch lifecycle -----
    {
        "name": "agent_create_branch",
        "description": "Create a new branch with a human label. ``anchor_id`` optional — defaults to the trunk root.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 200},
                "anchor_id": {"type": "integer"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "agent_close_branch",
        "description": "Mark a branch closed. Tails stay in place (non-destructive); just flips ``branch_state``.",
        "parameters": {
            "type": "object",
            "properties": {
                "branch_id": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["branch_id"],
        },
    },
    {
        "name": "agent_activate_node",
        "description": "Set the agent's ``current_active_node_id`` (decision-680). Subsequent writes default to this anchor unless overridden.",
        "parameters": {
            "type": "object",
            "properties": {"node_id": {"type": "integer"}},
            "required": ["node_id"],
        },
    },
    {
        "name": "agent_activate_branch",
        "description": "Switch the active context to a branch's origin.",
        "parameters": {
            "type": "object",
            "properties": {"branch_id": {"type": "integer"}},
            "required": ["branch_id"],
        },
    },
    # ----- artifacts -----
    {
        "name": "agent_emit_artifact",
        "description": (
            "Emit a branch output (list, draft, link, …) with provenance."
            " Artifacts do NOT participate in gravity (decision-664) — use"
            " them for things you want to point at, not consolidate."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "artifact_type": {"type": "string"},
                "payload": {"type": "string"},
                "external_url": {"type": "string"},
                "branch_id": {"type": "integer"},
                "derived_from": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
            "required": ["artifact_type"],
        },
    },
    {
        "name": "agent_list_artifacts",
        "description": "List artifacts emitted by this agent. Filter by ``branch_id`` or ``artifact_type``.",
        "parameters": {
            "type": "object",
            "properties": {
                "branch_id": {"type": "integer"},
                "artifact_type": {"type": "string"},
            },
        },
    },
    {
        "name": "agent_get_artifact",
        "description": "Fetch one artifact by id.",
        "parameters": {
            "type": "object",
            "properties": {"artifact_id": {"type": "integer"}},
            "required": ["artifact_id"],
        },
    },
    {
        "name": "agent_artifact_provenance",
        "description": "Get the M:M provenance map of an artifact (which experience nodes derived it).",
        "parameters": {
            "type": "object",
            "properties": {"artifact_id": {"type": "integer"}},
            "required": ["artifact_id"],
        },
    },
    {
        "name": "agent_node_artifacts",
        "description": "Reverse lookup: artifacts that derive from a given node.",
        "parameters": {
            "type": "object",
            "properties": {"node_id": {"type": "integer"}},
            "required": ["node_id"],
        },
    },
    # ----- lift candidates (cross-pollination) -----
    {
        "name": "agent_review_lift_candidates",
        "description": "Pending cross-pollination candidates (decision-670). Each row carries matched origins + a proposed synthesis (often null — backend never synthesises by default).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "agent_confirm_lift",
        "description": (
            "Finalise a candidate. ``accept`` / ``edit_content`` require"
            " ``synthesized_content`` (you provide the merge — decision-692)"
            " and a ``target_trunk_parent_id`` (one of identity / principles"
            " / person_knowledge root, from ``agent_init``). ``reject`` is a"
            " graph no-op."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "integer"},
                "action": {"type": "string", "enum": list(LIFT_ACTIONS)},
                "synthesized_content": {"type": "string"},
                "target_trunk_parent_id": {"type": "integer"},
            },
            "required": ["candidate_id", "action"],
        },
    },
    {
        "name": "agent_request_synthesis_assistance",
        "description": (
            "Opt-in escape hatch (decision-672): ask the backend to call"
            " Mistral for the synthesis instead of doing it yourself. v1"
            " returns ``not_implemented``; reserved for a future background"
            " job."
        ),
        "parameters": {
            "type": "object",
            "properties": {"candidate_id": {"type": "integer"}},
            "required": ["candidate_id"],
        },
    },
    # ----- promotion conflicts -----
    {
        "name": "agent_review_promotion_conflicts",
        "description": (
            "Skills sitting at ``promotion_status='conflict_held'`` — promotion"
            " found a nearby trunk neighbour (>=0.85 cosine). Returns each"
            " conflict skill + its nearest neighbours."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "agent_resolve_promotion_conflict",
        "description": (
            "Resolve a conflict (decision-692): ``promote`` replaces the"
            " trunk neighbour; ``revert`` keeps the skill branch-local. Do"
            " any content merge yourself before promoting — backend won't."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "integer"},
                "action": {"type": "string", "enum": list(PROMOTION_ACTIONS)},
            },
            "required": ["skill_id", "action"],
        },
    },
    # ----- skills -----
    {
        "name": "agent_load_skill",
        "description": (
            "Explicit cross-load (decision-680). Bumps"
            " ``cross_branch_activation_count`` when the skill is in another"
            " branch and feeds the promotion threshold."
        ),
        "parameters": {
            "type": "object",
            "properties": {"skill_id": {"type": "integer"}},
            "required": ["skill_id"],
        },
    },
    {
        "name": "agent_list_skills",
        "description": "All crystallized skills with summary metadata (latest_version, activation count, note count).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "agent_skill_versions",
        "description": "Version history for a skill, newest first.",
        "parameters": {
            "type": "object",
            "properties": {"skill_id": {"type": "integer"}},
            "required": ["skill_id"],
        },
    },
    {
        "name": "agent_get_skill_version",
        "description": "One specific version of a skill.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "integer"},
                "version_number": {"type": "integer"},
            },
            "required": ["skill_id", "version_number"],
        },
    },
    {
        "name": "agent_get_skill_md",
        "description": "Pre-rendered Markdown for a skill: title + version footer + content + active notes grouped by type.",
        "parameters": {
            "type": "object",
            "properties": {"skill_id": {"type": "integer"}},
            "required": ["skill_id"],
        },
    },
    {
        "name": "agent_skill_notes",
        "description": "Active notes attached to a skill (oldest first). Pass ``include_superseded=true`` for the full history.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "integer"},
                "include_superseded": {"type": "boolean", "default": False},
            },
            "required": ["skill_id"],
        },
    },
    {
        "name": "agent_add_skill_note",
        "description": "Attach a note to a skill. Notes integrate into the skill body at the next re-crystallization (decision-675).",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "integer"},
                "content": {"type": "string", "maxLength": 5000},
                "note_type": {"type": "string", "enum": list(SKILL_NOTE_TYPES)},
            },
            "required": ["skill_id", "content", "note_type"],
        },
    },
    {
        "name": "agent_supersede_skill_note",
        "description": "Mark a single note superseded without re-crystallising (decision-675).",
        "parameters": {
            "type": "object",
            "properties": {"note_id": {"type": "integer"}},
            "required": ["note_id"],
        },
    },
    {
        "name": "agent_complete_re_crystallization",
        "description": (
            "Replace a skill's content with the merged version and bump its"
            " version. Pass ``integrated_note_ids`` for the notes you folded"
            " in (they get marked integrated)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "integer"},
                "new_content": {"type": "string"},
                "integrated_note_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
            "required": ["skill_id", "new_content"],
        },
    },
    {
        "name": "agent_review_re_crystallization",
        "description": "Skills past the re-crystallization hysteresis threshold (consolidation_delta + active_note_count + content_drift).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "agent_skill_activations",
        "description": "Per-skill activation timeline (task-356): explicit_cross_load + auto_surface events with source branch + timestamp.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "integer"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
            },
            "required": ["skill_id"],
        },
    },
]


def dispatch_tool(
    *,
    tool_name: str,
    args: dict[str, Any],
    client: ConPortClient,
    agent_uuid: str,
) -> str:
    """Dispatch a tool call. Sync, returns JSON string, never raises."""
    try:
        result = _do_dispatch(tool_name, args, client, agent_uuid)
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 — handler must never raise
        return json.dumps({"error": str(exc), "tool": tool_name}, ensure_ascii=False)


# Dispatch table — keep in sync with TOOL_SCHEMAS. Each entry takes the args
# dict and returns whatever JSON-encodable payload the client method emits.
_HANDLERS: dict[str, Callable[[ConPortClient, str, dict[str, Any]], Any]] = {
    # writes
    "agent_remember": lambda c, u, a: c.remember(
        u, a["content"], parent_id=a.get("parent_id"), branch_id=a.get("branch_id"),
    ),
    "agent_recall": lambda c, u, a: c.recall(
        u, a["query"],
        scope_root_id=a.get("scope_root_id"),
        limit=int(a.get("limit", 10)),
        offset=int(a.get("offset", 0)),
    ),
    "agent_reflect": lambda c, u, a: c.reflect(
        u, int(a["node_id"]), new_content=a.get("new_content"),
    ),
    # tree
    "agent_get_node": lambda c, u, a: c.get_node(u, int(a["node_id"])),
    "agent_list_branches": lambda c, u, a: c.list_branches(u, state=a.get("state")),
    "agent_walk_branch": lambda c, u, a: c.walk_branch(u, int(a["branch_id"])),
    # branches
    "agent_create_branch": lambda c, u, a: c.create_branch(
        u, a["name"], anchor_id=a.get("anchor_id"),
    ),
    "agent_close_branch": lambda c, u, a: c.close_branch(
        u, int(a["branch_id"]), reason=a.get("reason"),
    ),
    "agent_activate_node": lambda c, u, a: c.activate_node(u, int(a["node_id"])),
    "agent_activate_branch": lambda c, u, a: c.activate_branch(u, int(a["branch_id"])),
    # artifacts
    "agent_emit_artifact": lambda c, u, a: c.emit_artifact(
        u,
        artifact_type=a["artifact_type"],
        payload=a.get("payload"),
        external_url=a.get("external_url"),
        branch_id=a.get("branch_id"),
        derived_from=a.get("derived_from"),
    ),
    "agent_list_artifacts": lambda c, u, a: c.list_artifacts(
        u, branch_id=a.get("branch_id"), artifact_type=a.get("artifact_type"),
    ),
    "agent_get_artifact": lambda c, u, a: c.get_artifact(u, int(a["artifact_id"])),
    "agent_artifact_provenance": lambda c, u, a: c.artifact_provenance(
        u, int(a["artifact_id"]),
    ),
    "agent_node_artifacts": lambda c, u, a: c.node_artifacts(u, int(a["node_id"])),
    # lift
    "agent_review_lift_candidates": lambda c, u, _a: c.list_lift_candidates(u),
    "agent_confirm_lift": lambda c, u, a: c.confirm_lift(
        u,
        int(a["candidate_id"]),
        a["action"],
        synthesized_content=a.get("synthesized_content"),
        target_trunk_parent_id=a.get("target_trunk_parent_id"),
    ),
    "agent_request_synthesis_assistance": lambda c, u, a: c.request_synthesis_assistance(
        u, int(a["candidate_id"]),
    ),
    # promotion
    "agent_review_promotion_conflicts": lambda c, u, _a: c.list_promotion_conflicts(u),
    "agent_resolve_promotion_conflict": lambda c, u, a: c.resolve_promotion_conflict(
        u, int(a["skill_id"]), a["action"],
    ),
    # skills
    "agent_load_skill": lambda c, u, a: c.load_skill(u, int(a["skill_id"])),
    "agent_list_skills": lambda c, u, _a: c.list_skills(u),
    "agent_skill_versions": lambda c, u, a: c.skill_versions(u, int(a["skill_id"])),
    "agent_get_skill_version": lambda c, u, a: c.skill_version(
        u, int(a["skill_id"]), int(a["version_number"]),
    ),
    "agent_get_skill_md": lambda c, u, a: {"markdown": c.skill_md(u, int(a["skill_id"]))},
    "agent_skill_notes": lambda c, u, a: c.skill_notes(
        u, int(a["skill_id"]), include_superseded=bool(a.get("include_superseded", False)),
    ),
    "agent_add_skill_note": lambda c, u, a: c.add_skill_note(
        u, int(a["skill_id"]), a["content"], a["note_type"],
    ),
    "agent_supersede_skill_note": lambda c, u, a: c.supersede_skill_note(
        u, int(a["note_id"]),
    ),
    "agent_complete_re_crystallization": lambda c, u, a: c.complete_re_crystallization(
        u,
        int(a["skill_id"]),
        a["new_content"],
        integrated_note_ids=a.get("integrated_note_ids"),
    ),
    "agent_review_re_crystallization": lambda c, u, _a: c.review_re_crystallization(u),
    "agent_skill_activations": lambda c, u, a: c.skill_activations(
        u, int(a["skill_id"]), limit=int(a.get("limit", 100)),
    ),
}


def _do_dispatch(
    tool_name: str,
    args: dict[str, Any],
    client: ConPortClient,
    agent_uuid: str,
) -> Any:
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"unknown tool: {tool_name}"}
    return handler(client, agent_uuid, args)
