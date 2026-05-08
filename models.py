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
