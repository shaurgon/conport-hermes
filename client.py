"""Synchronous REST client for the ConPort agent-memory API.

Auth: Bearer cport_live_… (decision D483: API key over OAuth for headless agents).
Endpoints follow https://api.conport.app/openapi.json.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

import httpx

from .models import (
    AgentRecord,
    MemoryLinkRecord,
    MemoryRecord,
    ReflectResult,
)

_T = TypeVar("_T")


def _extract_list(data: object) -> list[MemoryRecord]:
    """ConPort API wraps lists under `results` (recall) or `memories` (list).

    Handles both, plus raw arrays. Empty/missing → [].
    """
    if isinstance(data, list):
        return cast(list[MemoryRecord], data)
    if isinstance(data, dict):
        for key in ("results", "memories", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return cast(list[MemoryRecord], value)
    return []


def _extract_named_list(data: object, key: str) -> list[Any]:
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        value = data.get(key)
        if isinstance(value, list):
            return list(value)
    return []


def _as(record_type: type[_T], payload: object) -> _T:
    """Narrow `r.json()` (Any) to a TypedDict shape — server contract."""
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object for {record_type.__name__}, got {type(payload).__name__}")
    return cast(_T, payload)


class ConPortClient:
    def __init__(self, base_url: str, api_key: str, *, default_timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "conport-hermes/0.3.0",
            },
            timeout=default_timeout,
        )

    def close(self) -> None:
        self._client.close()

    # --- agents ---

    def get_agent(self, agent_uuid: str) -> AgentRecord:
        r = self._client.get(f"/api/v1/agents/{agent_uuid}")
        r.raise_for_status()
        return _as(AgentRecord, r.json())

    def create_agent(self, name: str, *, agent_type: str = "worker") -> AgentRecord:
        r = self._client.post("/api/v1/agents", json={"name": name, "type": agent_type})
        r.raise_for_status()
        return _as(AgentRecord, r.json())

    # --- memories ---

    def recall(
        self,
        agent_uuid: str,
        query: str,
        *,
        limit: int = 5,
        memory_type: str | None = None,
        category: str | None = None,
        project_id: int | None = None,
        timeout: float | None = None,
    ) -> list[MemoryRecord]:
        params: dict[str, Any] = {"q": query, "limit": limit}
        if memory_type:
            params["memory_type"] = memory_type
        if category:
            params["category"] = category
        if project_id is not None:
            params["project_id"] = project_id
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/memories/recall",
            params=params,
            timeout=timeout if timeout is not None else self._client.timeout,
        )
        r.raise_for_status()
        return _extract_list(r.json())

    def remember(
        self,
        agent_uuid: str,
        content: str,
        *,
        memory_type: str = "fact",
        tags: list[str] | None = None,
        category: str = "resource",
        entity_ref: str | None = None,
        pinned: bool = False,
        project_id: int | None = None,
    ) -> MemoryRecord:
        payload: dict[str, Any] = {
            "content": content,
            "memory_type": memory_type,
            "tags": tags or [],
            "category": category,
            "pinned": pinned,
        }
        if entity_ref:
            payload["entity_ref"] = entity_ref
        if project_id is not None:
            payload["project_id"] = project_id
        r = self._client.post(f"/api/v1/agents/{agent_uuid}/memories", json=payload)
        r.raise_for_status()
        return _as(MemoryRecord, r.json())

    def forget(
        self, agent_uuid: str, memory_id: int, *, hard_delete: bool = False
    ) -> None:
        params = {"hard": "true"} if hard_delete else {}
        r = self._client.delete(
            f"/api/v1/agents/{agent_uuid}/memories/{memory_id}", params=params
        )
        r.raise_for_status()

    def supersede(
        self, agent_uuid: str, memory_id: int, *, by_memory_id: int
    ) -> MemoryRecord:
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/memories/{memory_id}/supersede",
            json={"by_memory_id": by_memory_id},
        )
        r.raise_for_status()
        return _as(MemoryRecord, r.json())

    def reflect(
        self,
        agent_uuid: str,
        scope: str = "day",
        *,
        project_id: int | None = None,
    ) -> ReflectResult:
        params: dict[str, Any] = {"scope": scope}
        if project_id is not None:
            params["project_id"] = project_id
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/memories/reflect",
            params=params,
        )
        r.raise_for_status()
        return _as(ReflectResult, r.json())

    def link_memories(
        self,
        agent_uuid: str,
        source_memory_id: int,
        target_memory_id: int,
        relation_type: str,
        *,
        similarity_score: float | None = None,
    ) -> MemoryLinkRecord:
        payload: dict[str, Any] = {
            "source_memory_id": source_memory_id,
            "target_memory_id": target_memory_id,
            "relation_type": relation_type,
        }
        if similarity_score is not None:
            payload["similarity_score"] = similarity_score
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/memories/links", json=payload
        )
        r.raise_for_status()
        return _as(MemoryLinkRecord, r.json())

    def list_memories(
        self,
        agent_uuid: str,
        *,
        memory_type: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        params: dict[str, Any] = {"limit": limit}
        if memory_type:
            params["memory_type"] = memory_type
        if category:
            params["category"] = category
        r = self._client.get(f"/api/v1/agents/{agent_uuid}/memories", params=params)
        r.raise_for_status()
        return _extract_list(r.json())
