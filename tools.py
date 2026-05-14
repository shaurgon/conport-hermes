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
TASK_STATUSES = ("TODO", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED")
SEARCH_ITEM_TYPES = (
    "decision",
    "pattern",
    "progress_entry",
    "context",
    "custom_data",
    "task",
    "document",
)
DOC_TYPES = (
    "spec",
    "runbook",
    "api_docs",
    "tutorial",
    "architecture",
    "meeting_notes",
    "other",
)
DOC_STATUSES = ("active", "archived")
DOC_PATCH_OPS_HELP = (
    "Patch operation. Each item must have an `op` field plus op-specific args:\n"
    "- {op:'set_content', content:str} — replace whole body\n"
    "- {op:'replace_section_body', heading:str, content:str} — heading like "
    "'## API' or '## A > ### B'; rewrites body of that section (incl. subsections)\n"
    "- {op:'append_to_section', heading:str, content:str} — append before first subsection\n"
    "- {op:'insert_section_after', heading:str, content:str} — insert markdown block after section\n"
    "- {op:'delete_section', heading:str} — delete section incl. subsections\n"
    "- {op:'find_replace', find:str, replace:str, replace_all?:bool} — literal find/replace"
)


NO_PROJECT_ERROR = "no project attached — call conport_attach_project(name=...) first"


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
    {
        "name": "conport_attach_project",
        "description": (
            "Attach to a ConPort project by name. Required before using any "
            "project-level tool (search/tasks/decisions/progress/documents). "
            "Scope persists for the rest of the session."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Project name or numeric ID"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "conport_search",
        "description": (
            "Search across the attached project's content (decisions, patterns, "
            "tasks, documents, progress, context). Semantic + FTS hybrid."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "item_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(SEARCH_ITEM_TYPES)},
                    "description": "Restrict results to these item types",
                },
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["query"],
        },
    },
    {
        "name": "conport_add_task",
        "description": "Create a task in the attached project.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "maxLength": 200},
                "description": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": list(TASK_STATUSES),
                    "default": "TODO",
                },
                "priority": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
                "parent_task_id": {"type": "integer"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "conport_update_task",
        "description": (
            "Update a task. On status=DONE/CANCELLED pass `resolution` to record "
            "the verdict (auto-logs a progress entry; do NOT call conport_log_progress "
            "separately for task closes)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string", "enum": list(TASK_STATUSES)},
                "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                "parent_task_id": {"type": "integer"},
                "resolution": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "conport_list_tasks",
        "description": "List tasks in the attached project. Default: TODO + IN_PROGRESS.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": (
                        "Comma-separated statuses (e.g. 'TODO,IN_PROGRESS') or 'ALL'"
                    ),
                    "default": "TODO,IN_PROGRESS",
                },
                "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
        },
    },
    {
        "name": "conport_sync_decision",
        "description": (
            "Record an architectural decision with rationale and tags in the attached project."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "maxLength": 200},
                "rationale": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary"],
        },
    },
    {
        "name": "conport_log_progress",
        "description": (
            "Log a standalone progress entry (NOT for task closes — those auto-log "
            "via conport_update_task with resolution=...)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "title": {"type": "string", "maxLength": 200},
                "parent_id": {"type": "integer"},
                "linked_item_type": {
                    "type": "string",
                    "enum": ["task", "decision", "pattern"],
                },
                "linked_item_id": {"type": "integer"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "conport_get_document",
        "description": "Fetch a document from the attached project by per-project document_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer"},
                "raw": {
                    "type": "boolean",
                    "default": False,
                    "description": "Return unmodified markdown (skip Wave 5 stub injection)",
                },
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "conport_list_documents",
        "description": "List documents in the attached project, optionally filtered by doc_type.",
        "parameters": {
            "type": "object",
            "properties": {
                "doc_type": {"type": "string", "enum": list(DOC_TYPES)},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
        },
    },
    {
        "name": "conport_add_document",
        "description": (
            "Create a new document in the attached project. Search first to avoid "
            "duplicates — prefer conport_update_document or a callout-linked addendum "
            "over creating overlapping docs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string", "description": "Full markdown body"},
                "doc_type": {
                    "type": "string",
                    "enum": list(DOC_TYPES),
                    "default": "spec",
                },
                "parent_document_id": {"type": "integer"},
                "author": {"type": "string"},
                "external_url": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "conport_update_document",
        "description": (
            "Update a document. Pass content=<full markdown> to replace the body — "
            "the block reconciliation engine keeps unchanged blocks (and their "
            "embeddings/entity mentions), re-embeds dirty blocks, drops removed "
            "ones. Metadata fields (title, doc_type, tags, ...) can be updated "
            "without content. For single-block surgical edits, prefer "
            "conport_update_block (skips the document-wide reconcile)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer"},
                "title": {"type": "string"},
                "content": {
                    "type": "string",
                    "description": "Full markdown body — replaces the document content.",
                },
                "doc_type": {"type": "string", "enum": list(DOC_TYPES)},
                "parent_document_id": {"type": "integer"},
                "author": {"type": "string"},
                "external_url": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string", "enum": list(DOC_STATUSES)},
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "conport_get_block",
        "description": "Read one block by ULID from a document.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer"},
                "block_ulid": {"type": "string", "description": "Block ULID."},
            },
            "required": ["document_id", "block_ulid"],
        },
    },
    {
        "name": "conport_update_block",
        "description": (
            "Replace one block's markdown without touching the surrounding document. "
            "Use this for surgical edits — beats conport_update_document(content=...) "
            "for single-block changes because it doesn't re-embed every block."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer"},
                "block_ulid": {"type": "string"},
                "markdown": {
                    "type": "string",
                    "description": "New markdown text for this block.",
                },
            },
            "required": ["document_id", "block_ulid", "markdown"],
        },
    },
    {
        "name": "conport_insert_block",
        "description": (
            "Insert a new block into a document. Pass after=<ulid> or before=<ulid> "
            "to position; omit both to append at the end."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer"},
                "markdown": {"type": "string"},
                "after": {"type": "string", "description": "ULID to insert after (mutually exclusive with before)."},
                "before": {"type": "string", "description": "ULID to insert before (mutually exclusive with after)."},
            },
            "required": ["document_id", "markdown"],
        },
    },
    {
        "name": "conport_delete_block",
        "description": "Delete one block by ULID. Returns 404 if the block doesn't exist.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer"},
                "block_ulid": {"type": "string"},
            },
            "required": ["document_id", "block_ulid"],
        },
    },
]


def dispatch_tool(
    *,
    tool_name: str,
    args: dict[str, Any],
    client: ConPortClient,
    agent_uuid: str,
    project_id: int | None = None,
) -> str:
    """Dispatch a tool call.

    `conport_attach_project` is intentionally not handled here — it requires
    write access to provider session state, so the provider's
    ``handle_tool_call`` intercepts it before calling dispatch.
    """
    try:
        result = _do_dispatch(tool_name, args, client, agent_uuid, project_id)
        return json.dumps(result)
    except Exception as exc:  # noqa: BLE001 — handler must never raise
        return json.dumps({"error": str(exc), "tool": tool_name})


def _require_project(project_id: int | None) -> int:
    if project_id is None:
        raise RuntimeError(NO_PROJECT_ERROR)
    return project_id


def _do_dispatch(
    tool_name: str,
    args: dict[str, Any],
    client: ConPortClient,
    agent_uuid: str,
    project_id: int | None,
) -> Any:
    # --- agent memory ---
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
    # --- project tools ---
    if tool_name == "conport_search":
        return client.search(
            query=args["query"],
            project_id=_require_project(project_id),
            limit=args.get("limit", 20),
            item_types=args.get("item_types"),
            tags=args.get("tags"),
        )
    if tool_name == "conport_add_task":
        return client.create_task(
            project_id=_require_project(project_id),
            title=args["title"],
            description=args.get("description"),
            status=args.get("status", "TODO"),
            priority=args.get("priority", 3),
            parent_task_id=args.get("parent_task_id"),
        )
    if tool_name == "conport_update_task":
        return client.update_task(
            project_id=_require_project(project_id),
            task_id=args["task_id"],
            title=args.get("title"),
            description=args.get("description"),
            status=args.get("status"),
            priority=args.get("priority"),
            parent_task_id=args.get("parent_task_id"),
            resolution=args.get("resolution"),
        )
    if tool_name == "conport_list_tasks":
        return client.list_tasks(
            project_id=_require_project(project_id),
            status=args.get("status", "TODO,IN_PROGRESS"),
            priority=args.get("priority"),
            limit=args.get("limit", 50),
        )
    if tool_name == "conport_sync_decision":
        return client.create_decision(
            project_id=_require_project(project_id),
            summary=args["summary"],
            rationale=args.get("rationale"),
            tags=args.get("tags"),
        )
    if tool_name == "conport_log_progress":
        return client.create_progress(
            project_id=_require_project(project_id),
            description=args["description"],
            title=args.get("title"),
            parent_id=args.get("parent_id"),
            linked_item_type=args.get("linked_item_type"),
            linked_item_id=args.get("linked_item_id"),
        )
    if tool_name == "conport_get_document":
        return client.get_document(
            project_id=_require_project(project_id),
            document_id=args["document_id"],
            raw=args.get("raw", False),
        )
    if tool_name == "conport_list_documents":
        return client.list_documents(
            project_id=_require_project(project_id),
            doc_type=args.get("doc_type"),
            limit=args.get("limit", 50),
        )
    if tool_name == "conport_add_document":
        return client.create_document(
            project_id=_require_project(project_id),
            title=args["title"],
            content=args["content"],
            doc_type=args.get("doc_type", "spec"),
            parent_document_id=args.get("parent_document_id"),
            author=args.get("author"),
            external_url=args.get("external_url"),
            tags=args.get("tags"),
        )
    if tool_name == "conport_update_document":
        return client.update_document(
            project_id=_require_project(project_id),
            document_id=args["document_id"],
            title=args.get("title"),
            content=args.get("content"),
            doc_type=args.get("doc_type"),
            parent_document_id=args.get("parent_document_id"),
            author=args.get("author"),
            external_url=args.get("external_url"),
            tags=args.get("tags"),
            status=args.get("status"),
        )
    if tool_name == "conport_get_block":
        return client.get_block(
            project_id=_require_project(project_id),
            document_id=args["document_id"],
            block_ulid=args["block_ulid"],
        )
    if tool_name == "conport_update_block":
        return client.update_block(
            project_id=_require_project(project_id),
            document_id=args["document_id"],
            block_ulid=args["block_ulid"],
            markdown=args["markdown"],
        )
    if tool_name == "conport_insert_block":
        return client.insert_block(
            project_id=_require_project(project_id),
            document_id=args["document_id"],
            markdown=args["markdown"],
            after=args.get("after"),
            before=args.get("before"),
        )
    if tool_name == "conport_delete_block":
        client.delete_block(
            project_id=_require_project(project_id),
            document_id=args["document_id"],
            block_ulid=args["block_ulid"],
        )
        return {"deleted": True}
    raise ValueError(f"Unknown tool: {tool_name}")
