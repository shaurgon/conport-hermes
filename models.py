"""TypedDict shapes for ConPort REST responses and on-disk config.

Kept narrow on purpose: only the fields conport-hermes actually reads.
Server may add more — `total=False` lets unknown keys flow through.
"""

from __future__ import annotations

from typing import TypedDict


class AgentRecord(TypedDict, total=False):
    uuid: str
    agent_uuid: str
    name: str
    type: str
    memory_count: int


class MemoryRecord(TypedDict, total=False):
    id: int
    memory_type: str
    content: str
    category: str
    tags: list[str]
    pinned: bool
    created_at: str


class MemoryLinkRecord(TypedDict, total=False):
    id: int
    source_memory_id: int
    target_memory_id: int
    relation_type: str
    similarity_score: float


class ReflectResult(TypedDict, total=False):
    scope: str
    memories_processed: int
    summary: str


class ProviderConfig(TypedDict, total=False):
    api_base_url: str
    recall_limit: int
    recall_timeout_seconds: float


class IdentityFile(TypedDict, total=False):
    agent_uuid: str
    agent_name: str


class ProjectRecord(TypedDict, total=False):
    id: int
    name: str
    description: str
    created_at: str
    updated_at: str


class TaskRecord(TypedDict, total=False):
    id: int
    project_id: int
    title: str
    description: str
    status: str
    priority: int
    parent_task_id: int
    created_at: str
    updated_at: str


class DecisionRecord(TypedDict, total=False):
    id: int
    project_id: int
    summary: str
    rationale: str
    tags: list[str]
    created_at: str


class ProgressRecord(TypedDict, total=False):
    id: int
    project_id: int
    title: str
    description: str
    parent_id: int
    linked_item_type: str
    linked_item_id: int
    created_at: str


class DocumentRecord(TypedDict, total=False):
    id: int
    project_id: int
    title: str
    content: str
    doc_type: str
    tags: list[str]
    version: int
    created_at: str
    updated_at: str


class SearchResultRecord(TypedDict, total=False):
    item_type: str
    item_id: int
    project_id: int
    project_name: str
    score: float
    content: dict[str, object]
    created_at: str
