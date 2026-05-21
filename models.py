"""TypedDict shapes for ConPort REST responses and on-disk config.

Kept narrow on purpose: only the fields conport-hermes actually reads.
Server may add more — ``total=False`` lets unknown keys flow through.

v1.0.0: project-shaped records were removed in v0.6.0; v1 flat-memory
records (MemoryRecord/MemoryLinkRecord/ReflectResult v1) removed in
v1.0.0 alongside the move to Agent Memory v2's tree surface
(decisions 660–682). See ``client.py`` for the v2 wire shapes.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentRecord(TypedDict, total=False):
    uuid: str
    agent_uuid: str
    name: str
    type: str
    memory_count: int


class TrunkContextNode(TypedDict, total=False):
    id: int
    role: str  # trunk_root | identity_root | principles_root | person_knowledge_root
    content: str
    direct_children_count: int


class AgentInitPayload(TypedDict, total=False):
    """Response of ``POST /agents/{uuid}/init`` (decision-681)."""
    agent_uuid: str
    name: str
    type: str
    bootstrap_state: str  # 'new' | 'continuing'
    trunk_root_id: int
    identity_root_id: int
    principles_root_id: int
    person_knowledge_root_id: int
    current_active_node_id: int
    trunk_context: list[TrunkContextNode]
    active_branches: list[dict[str, Any]]
    recently_crystallized_skills: list[dict[str, Any]]
    pending_lift_candidates: int
    pending_promotion_conflicts: int
    summary: str


class AgentNodeChild(TypedDict, total=False):
    id: int
    content_preview: str
    branch_id: int | None
    is_skill: bool


class AgentNodeResponse(TypedDict, total=False):
    id: int
    agent_uuid: str
    content: str
    tags: list[str]
    parent_id: int | None
    depth: int | None
    branch_id: int | None
    branch_state: str | None
    is_skill: bool
    promotion_status: str
    direct_children_count: int
    consolidation_count: int
    children: list[AgentNodeChild]


class BranchSummary(TypedDict, total=False):
    branch_id: int
    branch_state: str
    origin_content_preview: str
    direct_children_count: int
    last_content_change_at: str | None
    is_skill: bool


class RecallHit(TypedDict, total=False):
    id: int
    content: str
    parent_id: int | None
    branch_id: int | None
    depth: int | None
    is_skill: bool
    similarity: float
    composite_score: float


class ProviderConfig(TypedDict, total=False):
    api_base_url: str
    recall_limit: int
    recall_timeout_seconds: float


class IdentityFile(TypedDict, total=False):
    agent_uuid: str
    agent_name: str
