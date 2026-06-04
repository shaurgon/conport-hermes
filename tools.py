"""Tool handlers — what runs when the agent invokes a tool.

Per Hermes contract: handler is sync and returns a JSON string (never raises).

The schemas (what the LLM sees) live in ``schemas.py``; this module wires each
schema name to a ``ConPortClient`` call. ``TOOL_SCHEMAS`` is re-exported here so
``from .tools import TOOL_SCHEMAS`` keeps working.

v4.0.0 — Agent Intent-API (doc-101): create_kind / get_kind / remember / event /
recall + aux (chat intake, subgraph, timeline, cleanup, runs, skill promotion).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .client import ConPortClient
from .schemas import TOOL_SCHEMAS

__all__ = ["TOOL_SCHEMAS", "dispatch_tool"]


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
    # intent verbs
    "agent_create_kind": lambda c, u, a: c.create_kind(
        u, a["name"], list(a["fields"]), a.get("statuses"), a.get("refs"),
    ),
    "agent_get_kind": lambda c, u, a: c.get_kind(u, a["name"]) or {},
    "agent_get_referrers": lambda c, u, a: c.get_referrers(a["kind"], a["name"]),
    "agent_remember": lambda c, u, a: c.remember(
        u,
        a.get("content"),
        meta_type=a.get("meta_type"),
        visibility=a.get("visibility"),
        edges=a.get("edges"),
        kind=a.get("kind"),
        name=a.get("name"),
        fields=a.get("fields"),
    ),
    "agent_event": lambda c, u, a: c.event(
        u,
        a["kind"],
        a["name"],
        a["note"],
        fields=a.get("fields"),
        event_type=a.get("event_type", "note"),
    ),
    "agent_recall": lambda c, u, a: c.recall(
        u,
        a["query"],
        limit=int(a.get("limit", 10)),
        scope=a.get("scope"),
    ),
    # skills: authored loops
    "agent_write_skill": lambda c, u, a: c.write_skill(u, a["name"], a["description"], a["body"]),
    "agent_get_skill": lambda c, u, a: c.get_skill(a["name"]) or {},
    # aux: conversation intake
    "agent_chat_turn": lambda c, u, a: c.chat_turn(u, a["role"], a["text"]),
    "agent_extract_thread": lambda c, u, a: c.extract_thread(u, list(a["message_ids"])),
    # aux: explore / timeline / cleanup
    "agent_get_subgraph": lambda c, u, a: c.get_subgraph(
        u, int(a["root_node_id"]), depth=int(a.get("depth", 2)),
    ),
    "agent_entity_delete": lambda c, u, a: c.entity_delete(a["kind"], a["name"]),
    "agent_event_query": lambda c, u, a: c.event_query(
        entity_id=a.get("entity_id"),
        event_type=a.get("event_type"),
        run_id=a.get("run_id"),
        limit=int(a.get("limit", 100)),
    ),
    # aux: skill promotion (a remember of a broadcast skill node)
    "agent_promote_skill": lambda c, u, a: c.remember(
        u,
        a["content"],
        meta_type="skill",
        visibility="broadcast",
        edges=[{"target_node_id": int(a["community_id"]), "edge_type": "skill_of"}],
    ),
    # aux: runs
    "agent_run_start": lambda c, u, a: c.run_start(u, a["skill_name"], params=a.get("params")),
    "agent_run_finish": lambda c, u, a: c.run_finish(
        int(a["run_id"]), a["status"], outputs=a.get("outputs"),
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
