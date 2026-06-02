"""Tool schemas exposed via ``MemoryProvider.get_tool_schemas`` /
``handle_tool_call``.

Per Hermes contract: handler is sync and returns a JSON string (never raises).

v2.0.0 — Agent Memory v3 sphere graph + Workspace v1 surface (18 tools).
All v2 tree-based tools removed (parent_id, branch_id, artifacts, lift,
promotion conflicts, skills versioning — see CHANGELOG.md for mapping).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .client import ConPortClient


TOOL_SCHEMAS: list[dict[str, Any]] = [
    # ── Memory: write ────────────────────────────────────────────────

    {
        "name": "agent_remember",
        "description": (
            "Persist a typed memory node in the sphere graph. "
            "Choose meta_type carefully: 'identity' and 'principle' are "
            "always forced private; 'fact'/'observation'/'artifact' default "
            "to shared; 'skill' defaults to broadcast. "
            "Pass edges to connect to existing nodes immediately — edge "
            "density is what creates topic structure in the sphere."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "meta_type": {
                    "type": "string",
                    "enum": ["identity", "principle", "fact", "observation", "skill", "artifact"],
                },
                "content": {"type": "string", "maxLength": 10000},
                "visibility": {
                    "type": "string",
                    "enum": ["private", "shared", "broadcast"],
                },
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target_node_id": {"type": "integer"},
                            "edge_type": {
                                "type": "string",
                                "enum": [
                                    "semantic",
                                    "derived_from",
                                    "temporal",
                                    "skill_of",
                                    "competing_view",
                                    "supersedes",
                                ],
                            },
                        },
                        "required": ["target_node_id", "edge_type"],
                    },
                },
            },
            "required": ["meta_type", "content"],
        },
    },

    {
        "name": "agent_recall",
        "description": (
            "Multi-strategy search (vector + keyword/FTS + graph adjacency, "
            "fused via RRF) across the sphere graph. Always call this before "
            "answering any question about prior context — the sphere stores "
            "more than the context window holds. Use scope to narrow by "
            "meta_type, visibility, community_id, or a since/until time range."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                "scope": {
                    "type": "object",
                    "properties": {
                        "meta_types": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "visibility": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "community_id": {"type": "integer"},
                        "since": {
                            "type": "string",
                            "description": "ISO 8601 timestamp — created_at >= since",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO 8601 timestamp — created_at <= until",
                        },
                    },
                },
            },
            "required": ["query"],
        },
    },

    {
        "name": "agent_chat_turn",
        "description": (
            "Record a single message in the conversation buffer. "
            "Call this for EVERY turn (user and assistant). "
            "When the response includes extraction_signal=true (buffer >= 10 "
            "un-extracted messages), call agent_extract_thread IMMEDIATELY "
            "with the returned message_ids before your next agent_remember."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": ["user", "assistant", "system"]},
                "text": {"type": "string"},
            },
            "required": ["role", "text"],
        },
    },

    {
        "name": "agent_extract_thread",
        "description": (
            "Extract typed memory nodes from a buffer of chat messages. "
            "Call this as soon as extraction_signal fires in agent_chat_turn. "
            "Pass the message_ids list from pending_extraction (returned by "
            "agent_init or agent_chat_turn). "
            "Extraction distills the conversation into typed sphere nodes "
            "with edges — facts, observations, principles, artifacts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 1,
                },
            },
            "required": ["message_ids"],
        },
    },

    {
        "name": "agent_get_subgraph",
        "description": (
            "BFS outward from a node through typed edges. "
            "Use after agent_recall found a relevant node and you want to "
            "explore its neighbourhood: 'what else is connected to this topic?' "
            "Filter by edge_types to follow only specific relationship kinds."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "root_node_id": {"type": "integer"},
                "depth": {"type": "integer", "minimum": 1, "maximum": 5, "default": 2},
                "edge_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "semantic",
                            "derived_from",
                            "temporal",
                            "skill_of",
                            "competing_view",
                            "supersedes",
                        ],
                    },
                },
            },
            "required": ["root_node_id"],
        },
    },

    {
        "name": "agent_promote_skill",
        "description": (
            "Promote a mature community into a broadcast skill node. "
            "Only call this when agent_init returns a community in "
            "mature_communities (>= 5 nodes, avg edge weight >= 1.5, "
            ">= 3 frozen members). Review the central_nodes, synthesize "
            "the pattern yourself, then call with your content. "
            "Skills are always broadcast — visible to all agents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "community_id": {"type": "integer"},
                "content": {
                    "type": "string",
                    "maxLength": 10000,
                    "description": "The synthesized skill content you wrote based on the community's central nodes.",
                },
            },
            "required": ["community_id", "content"],
        },
    },

    # ── Workspace: entity ────────────────────────────────────────────

    {
        "name": "agent_entity_upsert",
        "description": (
            "Create or merge a typed workspace entity (natural key: "
            "entity_type + name). Use for structured domain objects with "
            "numeric or stable attributes: cities, topics, people records, "
            "tracked items. attrs merge on upsert — new keys added, "
            "existing keys overwritten. "
            "Not for free-text observations — use agent_remember for those."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "name": {"type": "string"},
                "attrs": {"type": "object"},
            },
            "required": ["entity_type", "name"],
        },
    },

    {
        "name": "agent_entity_get",
        "description": "Look up a single workspace entity by natural key (entity_type + name).",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["entity_type", "name"],
        },
    },

    {
        "name": "agent_entity_list",
        "description": "List workspace entities of a given type.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
            },
            "required": ["entity_type"],
        },
    },

    # ── Workspace: event ─────────────────────────────────────────────

    {
        "name": "agent_event_record",
        "description": (
            "Append an immutable event to the workspace event log. "
            "Events are the raw time-series feed — news, measurements, "
            "user actions, external signals. Always append-only: once "
            "written, an event cannot be changed. "
            "Pass entity_id to associate with a workspace entity. "
            "Pass occurred_at (ISO 8601) when the real-world time differs "
            "from recording time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_type": {"type": "string"},
                "payload": {"type": "object"},
                "entity_id": {"type": "integer"},
                "occurred_at": {"type": "string", "description": "ISO 8601 datetime"},
                "run_id": {"type": "integer"},
            },
            "required": ["event_type", "payload"],
        },
    },

    {
        "name": "agent_event_query",
        "description": (
            "Query the workspace event log with optional filters. "
            "Returns events in reverse-chronological order."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "integer"},
                "event_type": {"type": "string"},
                "run_id": {"type": "integer"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
            },
        },
    },

    # ── Workspace: run ───────────────────────────────────────────────

    {
        "name": "agent_run_start",
        "description": (
            "Start a skill execution trace (status=running). "
            "Call at the beginning of any multi-step workflow — "
            "daily refresh, research sweep, analysis batch. "
            "Returns a run_id to pass to agent_run_finish and "
            "agent_event_record / agent_projection_record for provenance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["skill_name"],
        },
    },

    {
        "name": "agent_run_finish",
        "description": (
            "Close a run with final status and optional outputs. "
            "status must be 'completed', 'failed', or 'cancelled'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "integer"},
                "status": {
                    "type": "string",
                    "enum": ["completed", "failed", "cancelled"],
                },
                "outputs": {"type": "object"},
            },
            "required": ["run_id", "status"],
        },
    },

    # ── Workspace: projection ────────────────────────────────────────

    {
        "name": "agent_projection_record",
        "description": (
            "Record a derived snapshot (projection) for a workspace entity. "
            "A projection is a point-in-time view computed from events — "
            "current score, aggregated state, conclusion. "
            "Always pass derived_from_event_ids listing ALL events that "
            "influenced this snapshot; this gives the full provenance trail."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "integer"},
                "projection_type": {"type": "string"},
                "value": {"type": "object"},
                "derived_from_event_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "derived_from_run_id": {"type": "integer"},
            },
            "required": ["entity_id", "projection_type", "value"],
        },
    },

    {
        "name": "agent_projection_current",
        "description": "Fetch the latest projection snapshot for an entity + projection_type pair.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "integer"},
                "projection_type": {"type": "string"},
            },
            "required": ["entity_id", "projection_type"],
        },
    },

    {
        "name": "agent_projection_history",
        "description": "Full snapshot history for an entity + projection_type, newest first.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "integer"},
                "projection_type": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
            },
            "required": ["entity_id", "projection_type"],
        },
    },

    # ── Cross-link ───────────────────────────────────────────────────

    {
        "name": "agent_link_node_to_entity",
        "description": (
            "Link a sphere graph memory node to a workspace entity. "
            "Use when an observation or fact in memory is directly about "
            "or derived from a workspace entity. "
            "link_type: 'mentions' (default), 'about', or 'derived_from'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {"type": "integer"},
                "entity_id": {"type": "integer"},
                "link_type": {
                    "type": "string",
                    "enum": ["mentions", "about", "derived_from"],
                    "default": "mentions",
                },
            },
            "required": ["node_id", "entity_id"],
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
    # memory writes
    "agent_remember": lambda c, u, a: c.remember(
        u,
        a["content"],
        meta_type=a.get("meta_type", "fact"),
        visibility=a.get("visibility"),
        edges=a.get("edges"),
    ),
    # memory reads
    "agent_recall": lambda c, u, a: c.recall(
        u,
        a["query"],
        limit=int(a.get("limit", 10)),
        scope=a.get("scope"),
    ),
    # chat turn buffer
    "agent_chat_turn": lambda c, u, a: c.chat_turn(u, a["role"], a["text"]),
    "agent_extract_thread": lambda c, u, a: c.extract_thread(u, list(a["message_ids"])),
    # subgraph
    "agent_get_subgraph": lambda c, u, a: c.get_subgraph(
        u,
        int(a["root_node_id"]),
        depth=int(a.get("depth", 2)),
    ),
    # skill promotion
    "agent_promote_skill": lambda c, u, a: c.remember(
        u,
        a["content"],
        meta_type="skill",
        visibility="broadcast",
        edges=[{"target_node_id": int(a["community_id"]), "edge_type": "skill_of"}],
    ),
    # workspace: entity
    "agent_entity_upsert": lambda c, u, a: c.entity_upsert(
        u,
        a["entity_type"],
        a["name"],
        a.get("attrs"),
    ),
    "agent_entity_get": lambda c, u, a: c.entity_get(a["entity_type"], a["name"]) or {},
    "agent_entity_list": lambda c, u, a: c.entity_list(
        a["entity_type"],
        limit=int(a.get("limit", 50)),
    ),
    # workspace: event
    "agent_event_record": lambda c, u, a: c.event_record(
        u,
        a["event_type"],
        a["payload"],
        entity_id=a.get("entity_id"),
        occurred_at=a.get("occurred_at"),
        run_id=a.get("run_id"),
    ),
    "agent_event_query": lambda c, u, a: c.event_query(
        entity_id=a.get("entity_id"),
        event_type=a.get("event_type"),
        run_id=a.get("run_id"),
        limit=int(a.get("limit", 100)),
    ),
    # workspace: run
    "agent_run_start": lambda c, u, a: c.run_start(u, a["skill_name"], params=a.get("params")),
    "agent_run_finish": lambda c, u, a: c.run_finish(
        int(a["run_id"]),
        a["status"],
        outputs=a.get("outputs"),
    ),
    # workspace: projection
    "agent_projection_record": lambda c, u, a: c.projection_record(
        u,
        int(a["entity_id"]),
        a["projection_type"],
        a["value"],
        derived_from_event_ids=a.get("derived_from_event_ids"),
        derived_from_run_id=a.get("derived_from_run_id"),
    ),
    "agent_projection_current": lambda c, u, a: c.projection_current(
        int(a["entity_id"]),
        a["projection_type"],
    ) or {},
    "agent_projection_history": lambda c, u, a: c.projection_history(
        int(a["entity_id"]),
        a["projection_type"],
        limit=int(a.get("limit", 100)),
    ),
    # cross-link
    "agent_link_node_to_entity": lambda c, u, a: c.link_node_to_entity(
        u,
        int(a["node_id"]),
        int(a["entity_id"]),
        a.get("link_type", "mentions"),
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
