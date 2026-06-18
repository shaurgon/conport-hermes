"""Tool schemas — what the LLM sees (the agent-facing intent surface).

v4.0.0 — Agent Intent-API (doc-101). The agent works with intent verbs
(create_kind / get_kind / remember / link / event / recall); ConPort owns
storage. The old storage primitives (entity_upsert/get/list, event_record,
projection_*, link_node_to_entity) are gone from the surface — ``remember(kind,…)``
writes a structured item, ``event`` logs its changes, ``recall`` finds
everything; connections are auto-built by ConPort by meaning and can be asserted
explicitly with ``remember(edges=…)`` / ``link``. A few aux verbs remain for
needs the core don't cover (chat intake, timeline, cleanup, runs, skill promotion).

Schemas live here; their handlers (the dispatch table that wires each schema to
a ``ConPortClient`` call) live in ``tools.py``. ``get_tool_schemas`` returns
this list; ``handle_tool_call`` routes through ``tools.dispatch_tool``.
"""

from __future__ import annotations

from typing import Any


TOOL_SCHEMAS: list[dict[str, Any]] = [
    # ── The five intent verbs ─────────────────────────────────────────

    {
        "name": "agent_create_kind",
        "description": (
            "Declare a structured domain (a 'kind') once — like creating a "
            "table. Use when you'll track many items of one sort that you "
            "filter/compare/update over time (cities you score, series you "
            "rate, research topics). 'fields' is the shape items carry; "
            "'statuses' is the controlled lifecycle vocabulary (enforced on "
            "write). 'refs' declares typed references to other kinds — "
            "{field: target_kind} (e.g. a 'source' kind with refs={topic: "
            "'topic'}); a field can also name a LIST of items of one kind via "
            "{field: {kind: target_kind, multi: true}}. The ref field is "
            "validated on every write (each element must name a real item of "
            "the target kind, or you get unknown_ref). Pick ONE "
            "canonical name per domain; check agent_init.collections first so "
            "you reuse an existing kind instead of fragmenting it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Singular canonical kind name."},
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Field names items of this kind carry.",
                },
                "statuses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Allowed status values (controlled vocab).",
                },
                "refs": {
                    "type": "object",
                    "description": (
                        "Typed references, validated on write. Scalar form "
                        "{field_name: target_kind}, or array form "
                        "{field_name: {kind: target_kind, multi: true}} for a "
                        "field that names a list of items of one kind."
                    ),
                },
            },
            "required": ["name", "fields"],
        },
    },

    {
        "name": "agent_get_referrers",
        "description": (
            "Find the items that reference this one — exact provenance. Given an "
            "item (kind, name), return every item whose declared ref points at "
            "it (for ('topic','mcp-security') you get its 'source' items). Exact "
            "and exhaustive — use it to reconstruct what a synthesis rests on. "
            "Unlike recall (ranked, fuzzy), this follows the declared refs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "The referenced item's kind."},
                "name": {"type": "string", "description": "The referenced item's name."},
            },
            "required": ["kind", "name"],
        },
    },

    {
        "name": "agent_get_kind",
        "description": (
            "Read a kind's form — fields + statuses + member count — BEFORE "
            "writing items with agent_remember(kind=…). Use the real fields "
            "and a valid status instead of inventing them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
    },

    {
        "name": "agent_remember",
        "description": (
            "Keep something — ConPort routes by whether you pass 'kind'.\n"
            "• Free cognition: remember(content=…, meta_type=…) → a thought / "
            "fact / observation. meta_type: identity/principle (forced "
            "private) / fact / observation / skill / artifact. visibility: "
            "private / shared (default) / broadcast.\n"
            "• Structured item: remember(kind=…, name=…, fields=…) → the "
            "current state of an item in a declared kind. The 'status' field "
            "is validated against the kind's statuses; unknown fields are "
            "accepted (the schema grows). An item is ONE record — a "
            "list/wishlist is just its members filtered by status, not an "
            "item. A synthesis/verdict lives in the item's fields, not a "
            "separate object. remember(kind=…) into an undeclared kind fails "
            "with unknown_kind — create_kind first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "maxLength": 10000, "description": "Free-cognition text."},
                "meta_type": {
                    "type": "string",
                    "enum": ["identity", "principle", "fact", "observation", "skill", "artifact"],
                },
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
                                    "semantic", "derived_from", "temporal",
                                    "skill_of", "competing_view", "supersedes",
                                    "unifies", "introduces", "cites",
                                    "uses_method", "reports_finding", "refines",
                                ],
                            },
                            "properties": {
                                "type": "object",
                                "description": (
                                    "Optional edge metadata: confidence (0..1), "
                                    "source_item, evidence_section, note. "
                                    "Unknown keys allowed."
                                ),
                            },
                        },
                        "required": ["target_node_id", "edge_type"],
                    },
                    "description": "Optional connections (free-cognition form). Usually leave it to ConPort.",
                },
                "kind": {"type": "string", "description": "Declared kind name (structured-item form)."},
                "name": {"type": "string", "description": "Item name within the kind (structured-item form)."},
                "fields": {"type": "object", "description": "Item attributes incl. an optional 'status'."},
                "relevant_until": {
                    "type": "string",
                    "description": (
                        "Optional validity horizon, ISO 8601 (either form). "
                        "Past it the memory drops in recall rank — it is NOT "
                        "deleted. Set it for operationally-scoped notes "
                        "(days); leave unset for durable knowledge. The "
                        "special value 'clear' resets a previously set "
                        "horizon back to indefinite."
                    ),
                },
            },
        },
    },

    {
        "name": "agent_link",
        "description": (
            "Assert an explicit edge between two cognition nodes you already "
            "remembered. ConPort auto-links new memories by meaning, and "
            "remember(edges=…) connects a new node to existing ones — use "
            "agent_link for the remaining case: relating two nodes that BOTH "
            "already exist (a fact you recalled now belongs under a thesis you "
            "stated earlier). Node ids come from remember/recall. edge_type is "
            "one of 12 types — structural: 'supersedes' (source replaces "
            "target), 'derived_from' (source distilled from target), 'temporal' "
            "(time-ordered), 'competing_view', 'skill_of', 'semantic'; domain: "
            "'unifies', 'introduces', 'cites', 'uses_method', 'reports_finding', "
            "'refines'. Optional 'properties' carries edge metadata "
            "(confidence 0..1, source_item, evidence_section, note)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "from_node_id": {"type": "integer", "description": "Source node id (yours)."},
                "to_node_id": {"type": "integer", "description": "Target node id (yours)."},
                "edge_type": {
                    "type": "string",
                    "enum": [
                        "semantic", "derived_from", "temporal",
                        "skill_of", "competing_view", "supersedes",
                        "unifies", "introduces", "cites",
                        "uses_method", "reports_finding", "refines",
                    ],
                },
                "properties": {
                    "type": "object",
                    "description": (
                        "Optional edge metadata: confidence (0..1), "
                        "source_item, evidence_section, note. Unknown keys allowed."
                    ),
                },
            },
            "required": ["from_node_id", "to_node_id", "edge_type"],
        },
    },

    {
        "name": "agent_event",
        "description": (
            "Log a change / what-happened on an existing structured item — its "
            "append-only timeline (like a progress entry scoped to one item). "
            "Carries a human 'note' plus optional structured 'fields' (so a "
            "research checklist lands in the payload, not in prose). Separate "
            "from remember: state → remember, history → event. The item "
            "(kind, name) must already exist. Events are NOT returned by "
            "recall — read them with agent_event_query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "name": {"type": "string"},
                "note": {"type": "string", "description": "Human-readable description of what happened."},
                "fields": {"type": "object", "description": "Optional structured payload (e.g. a checklist)."},
                "event_type": {"type": "string", "description": "Event category for later filtering. Default 'note'."},
            },
            "required": ["kind", "name", "note"],
        },
    },

    {
        "name": "agent_recall",
        "description": (
            "Find anything relevant — free cognition AND structured items, one "
            "ranked typed list (each result has a 'type': 'node' or 'item'; an "
            "item's synthesis rides in its 'fields'). Always call this before "
            "answering any question about prior context — recall holds more "
            "than the context window. Use scope to narrow: meta_types, "
            "visibility, kind (only that domain's items), a since/until time "
            "range, or include_superseded. By default nodes replaced via "
            "supersedes edges (consolidation) are excluded — only the current "
            "version surfaces; set include_superseded=true to see history."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "intent": {
                    "type": "string",
                    "description": (
                        "Optional statement of what you're trying to "
                        "accomplish — sharpens ranking beyond topic "
                        "similarity (granularity, content-type, "
                        "current-vs-history). E.g. 'current state, not "
                        "history'. Leave unset for simple lookups."
                    ),
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "scope": {
                    "type": "object",
                    "properties": {
                        "meta_types": {"type": "array", "items": {"type": "string"}},
                        "visibility": {"type": "array", "items": {"type": "string"}},
                        "kind": {"type": "string", "description": "Restrict items to this kind."},
                        "community_id": {"type": "integer"},
                        "since": {"type": "string", "description": "ISO 8601 timestamp — created_at >= since"},
                        "until": {"type": "string", "description": "ISO 8601 timestamp — created_at <= until"},
                        "include_superseded": {
                            "type": "boolean",
                            "description": (
                                "Also return nodes replaced via supersedes edges "
                                "(excluded by default) — audit / history navigation."
                            ),
                        },
                    },
                },
            },
            "required": ["query"],
        },
    },

    # ── Skills: authored loops (body in storage, description for discovery) ──

    {
        "name": "agent_write_skill",
        "description": (
            "Author (or update) a reusable skill — your own loop / procedure. "
            "The body (full markdown — your loop steps) is kept in storage; the "
            "one-line description is what surfaces in agent_init and recall, so "
            "future-you finds it without reloading the whole text. When you keep "
            "doing the same structural work (nightly research, daily scoring), "
            "write it down once here instead of re-improvising."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Canonical skill name, e.g. 'dream-topic-loop'."},
                "description": {"type": "string", "description": "One line — when to run this and what it does."},
                "body": {"type": "string", "description": "The full procedure (markdown)."},
            },
            "required": ["name", "description", "body"],
        },
    },

    {
        "name": "agent_get_skill",
        "description": (
            "Fetch a skill's full body on demand — one loop, not the whole pile. "
            "Call when a skill description (from agent_init or recall) fits what "
            "you're about to do; pull the body and follow it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
    },

    # ── Aux: conversation intake ──────────────────────────────────────

    {
        "name": "agent_chat_turn",
        "description": (
            "Record a single message in the conversation buffer. Call for "
            "EVERY turn (user and assistant). When the response includes "
            "extraction_signal=true (buffer ≥ 10 un-extracted messages), call "
            "agent_extract_thread IMMEDIATELY with the returned message_ids "
            "before your next agent_remember."
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
            "Distill a buffer of chat messages into typed memories. Call as "
            "soon as extraction_signal fires in agent_chat_turn (or "
            "agent_init's pending_extraction). Pass the returned message_ids."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
            },
            "required": ["message_ids"],
        },
    },

    {
        "name": "agent_extract_into",
        "description": (
            "Batch-record memories YOU extracted from a source, with their "
            "provenance auto-wired. You did the reading and the extraction; this "
            "hands ConPort the finished nodes + edges in one call (no LLM runs "
            "server-side). Each new node is auto-linked 'derived_from' the "
            "source — so the provenance is never lost. Use after distilling a "
            "document/artifact into several facts/observations you want "
            "connected.\n"
            "Pick EXACTLY ONE source (else invalid_source):\n"
            "• a cognition NODE — 'item_id'; returns item_id + "
            "derived_from_created.\n"
            "• a WORKSPACE ITEM — either the ('item_kind','item_name') handle "
            "(e.g. kind 'research_source') OR its raw 'source_entity_id'; edges "
            "can't point at a workspace item so provenance rides the node↔item "
            "link instead. Returns entity_id + entity_links_created.\n"
            "'nodes' is a list of {content, meta_type?, visibility?}. 'edges' "
            "connect the new nodes by their INDEX in 'nodes': {from_index, "
            "to_index, edge_type, properties?} between two new nodes, or "
            "{from_index, target_node_id, edge_type, properties?} to a "
            "pre-existing node. A bad node aborts the whole batch; bad edges "
            "are reported per-edge in edge_errors without losing the nodes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "integer",
                    "description": (
                        "NODE source — an EXISTING cognition node of yours the "
                        "extractions derive from. Mutually exclusive with the "
                        "workspace-item source params (item_kind+item_name / "
                        "source_entity_id)."
                    ),
                },
                "item_kind": {
                    "type": "string",
                    "description": (
                        "WORKSPACE-ITEM source — the item's kind (its "
                        "entity_type, e.g. 'research_source'). Pair with "
                        "item_name."
                    ),
                },
                "item_name": {
                    "type": "string",
                    "description": (
                        "WORKSPACE-ITEM source — the item's name. Paired with "
                        "item_kind; resolved owner-scoped (item_not_found if no "
                        "such item is yours)."
                    ),
                },
                "source_entity_id": {
                    "type": "integer",
                    "description": (
                        "WORKSPACE-ITEM source — the raw item id, a convenience "
                        "alternative to the (item_kind, item_name) handle."
                    ),
                },
                "nodes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "maxLength": 10000},
                            "meta_type": {
                                "type": "string",
                                "enum": ["identity", "principle", "fact", "observation", "skill", "artifact"],
                            },
                            "visibility": {
                                "type": "string",
                                "enum": ["private", "shared", "broadcast"],
                            },
                        },
                        "required": ["content"],
                    },
                    "description": "The extracted memories. meta_type defaults to 'observation', visibility to 'shared'.",
                },
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from_index": {"type": "integer", "description": "Index into 'nodes' (source)."},
                            "to_index": {"type": "integer", "description": "Index into 'nodes' (target — new node)."},
                            "target_node_id": {"type": "integer", "description": "Target an EXISTING owned node instead of to_index."},
                            "edge_type": {
                                "type": "string",
                                "enum": [
                                    "semantic", "derived_from", "temporal",
                                    "skill_of", "competing_view", "supersedes",
                                    "unifies", "introduces", "cites",
                                    "uses_method", "reports_finding", "refines",
                                ],
                            },
                            "properties": {
                                "type": "object",
                                "description": (
                                    "Optional edge metadata: confidence (0..1), "
                                    "source_item, evidence_section, note."
                                ),
                            },
                        },
                        "required": ["from_index", "edge_type"],
                    },
                    "description": "Optional inter-node edges referencing the new nodes by index.",
                },
            },
            "required": ["nodes"],
        },
    },

    # ── Aux: explore / timeline / cleanup ─────────────────────────────

    {
        "name": "agent_get_subgraph",
        "description": (
            "Explore the neighbourhood of a cognition node found via recall: "
            "'what else is connected to this?' Pass the node_id from a recall "
            "result of type 'node'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "root_node_id": {"type": "integer"},
                "depth": {"type": "integer", "minimum": 1, "maximum": 4, "default": 2},
            },
            "required": ["root_node_id"],
        },
    },

    {
        "name": "agent_graph_stats",
        "description": (
            "Statistics over your OWN sphere graph: visible nodes/edges by "
            "type + workspace item count. The right tool for 'how big is my "
            "memory' — it counts exactly what agent_recall can retrieve. It "
            "does NOT measure the project knowledge graph."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },

    {
        "name": "agent_node_forget",
        "description": (
            "Forget one of YOUR memory nodes — hides it from recall/init "
            "permanently (the row is kept server-side; irreversible from "
            "here). Use after consolidation when an old node actively "
            "misleads; prefer supersedes edges when a replacement exists. "
            "For structured items use agent_entity_delete instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {"type": "integer", "description": "Node id from a recall result of type 'node'."},
            },
            "required": ["node_id"],
        },
    },

    {
        "name": "agent_node_mute",
        "description": (
            "Mute a node — hide someone else's noise from YOUR recall. "
            "Reversible (agent_node_unmute brings it back); the shared "
            "corpus is untouched, other agents still see it. Contrast: "
            "agent_node_forget is irreversible, creator-only, and hides "
            "from everyone — that one is for YOUR own noise."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {"type": "integer", "description": "Node id from a recall result of type 'node'."},
            },
            "required": ["node_id"],
        },
    },

    {
        "name": "agent_node_unmute",
        "description": (
            "Reverse a mute — a node you previously muted surfaces in your "
            "recall again. Idempotent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {"type": "integer"},
            },
            "required": ["node_id"],
        },
    },

    {
        "name": "agent_entity_delete",
        "description": (
            "Soft-delete a structured item by (kind, name) — to fix a "
            "mistake (wrong kind, duplicate) instead of leaving junk. Its "
            "events/timeline survive server-side, and re-remembering the "
            "same (kind, name) resurrects the item."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["kind", "name"],
        },
    },

    {
        "name": "agent_event_query",
        "description": (
            "Read a structured item's timeline (events aren't in recall). Pass "
            "the item_id from a recall result of type 'item' as entity_id. "
            "Returns events newest-first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "integer", "description": "The item_id from a recall result."},
                "event_type": {"type": "string"},
                "run_id": {"type": "integer"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
            },
        },
    },

    # ── Aux: skill emergence ──────────────────────────────────────────

    {
        "name": "agent_promote_skill",
        "description": (
            "Promote a mature community into a broadcast skill. Only when "
            "agent_init returns a community in mature_communities. Review its "
            "central_nodes, synthesize the pattern yourself, then call with "
            "your content. Skills are always broadcast."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "community_id": {"type": "integer"},
                "content": {
                    "type": "string",
                    "maxLength": 10000,
                    "description": "The synthesized skill content you wrote from the community's central nodes.",
                },
            },
            "required": ["community_id", "content"],
        },
    },

    # ── Aux: run (skill-execution tracking) ───────────────────────────

    {
        "name": "agent_run_start",
        "description": (
            "Start a skill execution trace (status=running). Wrap a multi-step "
            "workflow (daily refresh, research sweep). Returns a run_id for "
            "agent_run_finish."
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
            "Close a run with final status and optional outputs. status must "
            "be 'completed', 'failed', or 'cancelled'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "integer"},
                "status": {"type": "string", "enum": ["completed", "failed", "cancelled"]},
                "outputs": {"type": "object"},
            },
            "required": ["run_id", "status"],
        },
    },
]
