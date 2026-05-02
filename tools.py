"""Tool schemas exposed via MemoryProvider.get_tool_schemas / handle_tool_call.

Per Hermes contract: handler is sync and returns a JSON string (never raises).
"""

from __future__ import annotations

import json
from typing import Any

from .client import ConPortClient


MEMORY_TYPES = ("fact", "feedback", "pattern", "note", "tacit", "decision")
PARA_CATEGORIES = ("project", "area", "resource", "archive")
RELATION_TYPES = ("related_to", "supersedes", "derives_from", "contradicts", "supports")


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "conport_remember",
        "description": "Persist something durable: a decision, lesson, fact, or pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "maxLength": 10000},
                "memory_type": {
                    "type": "string",
                    "enum": list(MEMORY_TYPES),
                    "default": "fact",
                },
                "category": {
                    "type": "string",
                    "enum": list(PARA_CATEGORIES),
                    "default": "resource",
                },
                "tags": {"type": "array", "items": {"type": "string"}},
                "entity_ref": {"type": "string", "description": "Canonical entity name to link"},
                "pinned": {"type": "boolean", "default": False},
            },
            "required": ["content"],
        },
    },
    {
        "name": "conport_recall",
        "description": "Search prior memories with semantic + decay-aware scoring.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
                "memory_type": {"type": "string", "enum": list(MEMORY_TYPES)},
                "category": {"type": "string", "enum": list(PARA_CATEGORIES)},
            },
            "required": ["query"],
        },
    },
    {
        "name": "conport_forget",
        "description": "Remove a memory by id. Soft-delete by default; hard_delete=true purges.",
        "parameters": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer"},
                "hard_delete": {"type": "boolean", "default": False},
            },
            "required": ["memory_id"],
        },
    },
    {
        "name": "conport_reflect",
        "description": "Trigger reflection/synthesis: dedup, supersede, surface patterns. Scope: day, week, full.",
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["day", "week", "full"],
                    "default": "day",
                },
            },
        },
    },
    {
        "name": "conport_link_memories",
        "description": "Connect two memories with a typed relation (related_to, supersedes, derives_from, contradicts, supports).",
        "parameters": {
            "type": "object",
            "properties": {
                "source_memory_id": {"type": "integer"},
                "target_memory_id": {"type": "integer"},
                "relation_type": {"type": "string", "enum": list(RELATION_TYPES)},
                "similarity_score": {"type": "number"},
            },
            "required": ["source_memory_id", "target_memory_id", "relation_type"],
        },
    },
]


def dispatch_tool(
    *, tool_name: str, args: dict[str, Any], client: ConPortClient, agent_uuid: str
) -> str:
    try:
        result = _do_dispatch(tool_name, args, client, agent_uuid)
        return json.dumps(result)
    except Exception as exc:  # noqa: BLE001 — handler must never raise
        return json.dumps({"error": str(exc), "tool": tool_name})


def _do_dispatch(
    tool_name: str, args: dict[str, Any], client: ConPortClient, agent_uuid: str
) -> Any:
    if tool_name == "conport_remember":
        return client.remember(
            agent_uuid=agent_uuid,
            content=args["content"],
            memory_type=args.get("memory_type", "fact"),
            category=args.get("category", "resource"),
            tags=args.get("tags"),
            entity_ref=args.get("entity_ref"),
            pinned=args.get("pinned", False),
        )
    if tool_name == "conport_recall":
        return client.recall(
            agent_uuid=agent_uuid,
            query=args["query"],
            limit=args.get("limit", 5),
            memory_type=args.get("memory_type"),
            category=args.get("category"),
        )
    if tool_name == "conport_forget":
        client.forget(
            agent_uuid=agent_uuid,
            memory_id=args["memory_id"],
            hard_delete=args.get("hard_delete", False),
        )
        return {"ok": True, "memory_id": args["memory_id"]}
    if tool_name == "conport_reflect":
        return client.reflect(agent_uuid=agent_uuid, scope=args.get("scope", "day"))
    if tool_name == "conport_link_memories":
        return client.link_memories(
            agent_uuid=agent_uuid,
            source_memory_id=args["source_memory_id"],
            target_memory_id=args["target_memory_id"],
            relation_type=args["relation_type"],
            similarity_score=args.get("similarity_score"),
        )
    raise ValueError(f"Unknown tool: {tool_name}")
