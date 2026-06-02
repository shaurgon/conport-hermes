"""TypedDict shapes for ConPort REST/MCP responses and on-disk config.

v2.0.0: rewritten for Agent Memory v3 (sphere graph) + Workspace v1
(event-sourced records). All v2 tree-based types removed.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentRecord(TypedDict, total=False):
    uuid: str
    agent_uuid: str
    name: str
    type: str


# ── Memory v3 (sphere graph) ────────────────────────────────────────

class InitAnchor(TypedDict, total=False):
    id: int
    content: str
    created_at: str


class MatureCommunity(TypedDict, total=False):
    community_id: int
    node_count: int
    avg_edge_weight: float
    frozen_count: int
    central_nodes: list[dict[str, Any]]
    hint: str


class BorderlineNode(TypedDict, total=False):
    node_id: int
    content_preview: str
    communities_visited: list[int]


class PendingExtraction(TypedDict, total=False):
    buffer_size: int
    message_ids: list[int]


class Collection(TypedDict, total=False):
    key: str           # entity_type that IS the collection
    members: int
    description: str | None
    field_hints: list[str] | None
    status_vocab: list[str] | None


class AgentInitPayload(TypedDict, total=False):
    agent_uuid: str
    owner_id: str
    name: str
    type: str
    bootstrap_state: str  # 'new' | 'continuing'
    identity: list[InitAnchor]
    principles: list[InitAnchor]
    broadcast_facts: list[InitAnchor]
    mature_communities: list[MatureCommunity]
    borderline_nodes: list[BorderlineNode]
    pending_extraction: PendingExtraction | None
    collections: list[Collection]
    summary: str


class RecallHit(TypedDict, total=False):
    node_id: int
    content: str
    meta_type: str
    visibility: str
    frozen_community_id: int | None
    created_by_agent_uuid: str
    created_at: str
    similarity: float | None
    score: float


# ── Config ───────────────────────────────────────────────────────────

class ProviderConfig(TypedDict, total=False):
    api_base_url: str
    recall_limit: int
    recall_timeout_seconds: float


class IdentityFile(TypedDict, total=False):
    agent_uuid: str
    agent_name: str
