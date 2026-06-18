"""TypedDict shapes for ConPort REST responses and on-disk config.

v4.0.0: Agent Intent-API — the agent works with intent verbs over hidden
storage. ``RecallHit`` is a typed union (node | item); ``KindInfo`` is the
form returned by ``get_kind``.
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


class SkillDescriptor(TypedDict, total=False):
    name: str
    description: str | None   # body lives in storage, fetched via get_skill


class AgentInitPayload(TypedDict, total=False):
    agent_uuid: str
    owner_id: str
    name: str
    type: str
    bootstrap_state: str  # 'new' | 'continuing'
    identity: list[InitAnchor]
    principles: list[InitAnchor]
    broadcast_facts: list[InitAnchor]
    skills: list[SkillDescriptor]
    mature_communities: list[MatureCommunity]
    borderline_nodes: list[BorderlineNode]
    pending_extraction: PendingExtraction | None
    collections: list[Collection]
    summary: str


class RecallHit(TypedDict, total=False):
    """One recall result — a typed union of a cognition node OR a structured item.

    ``type`` discriminates: 'node' carries node_id/content/meta_type/visibility;
    'item' carries item_id/kind/name/fields (the item's current-state synthesis).
    """
    type: str  # 'node' | 'item'
    score: float
    created_by_agent_uuid: str
    created_at: str
    # node-shaped
    node_id: int
    content: str
    meta_type: str
    visibility: str
    frozen_community_id: int | None
    similarity: float | None
    # item-shaped
    item_id: int
    kind: str
    name: str
    fields: dict[str, Any]


class KindInfo(TypedDict, total=False):
    """The form of a structured domain, returned by ``get_kind``."""
    kind: str
    fields: list[str]
    statuses: list[str]
    refs: dict[str, Any]   # {field_name: target_kind} or {field_name: {kind, multi}} — typed references
    description: str | None
    count: int


# ── Config ───────────────────────────────────────────────────────────

class ProviderConfig(TypedDict, total=False):
    api_base_url: str
    recall_limit: int
    recall_timeout_seconds: float


class IdentityFile(TypedDict, total=False):
    agent_uuid: str
    agent_name: str
