"""Synchronous REST client for the ConPort agent-memory API.

Auth: Bearer cport_live_… (decision D483: API key over OAuth for headless agents).
Endpoints follow https://api.conport.app/openapi.json.
"""

from __future__ import annotations

from typing import Any

import httpx


def _extract_list(data: Any) -> list[dict[str, Any]]:
    """ConPort API wraps lists under `results` (recall) or `memories` (list).

    Handles both, plus raw arrays. Empty/missing → [].
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "memories", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


class ConPortClient:
    def __init__(self, base_url: str, api_key: str, *, default_timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "conport-hermes/0.1.7",
            },
            timeout=default_timeout,
        )

    def close(self) -> None:
        self._client.close()

    # --- agents ---

    def get_agent(self, agent_uuid: str) -> dict[str, Any]:
        r = self._client.get(f"/api/v1/agents/{agent_uuid}")
        r.raise_for_status()
        return r.json()

    def create_agent(self, name: str, *, agent_type: str = "worker") -> dict[str, Any]:
        r = self._client.post("/api/v1/agents", json={"name": name, "type": agent_type})
        r.raise_for_status()
        return r.json()

    # --- memories ---

    def recall(
        self,
        agent_uuid: str,
        query: str,
        *,
        limit: int = 5,
        memory_type: str | None = None,
        category: str | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"q": query, "limit": limit}
        if memory_type:
            params["memory_type"] = memory_type
        if category:
            params["category"] = category
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
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "content": content,
            "memory_type": memory_type,
            "tags": tags or [],
            "category": category,
            "pinned": pinned,
        }
        if entity_ref:
            payload["entity_ref"] = entity_ref
        r = self._client.post(f"/api/v1/agents/{agent_uuid}/memories", json=payload)
        r.raise_for_status()
        return r.json()

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
    ) -> dict[str, Any]:
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/memories/{memory_id}/supersede",
            json={"by_memory_id": by_memory_id},
        )
        r.raise_for_status()
        return r.json()

    def reflect(self, agent_uuid: str, scope: str = "day") -> dict[str, Any]:
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/memories/reflect",
            params={"scope": scope},
        )
        r.raise_for_status()
        return r.json()

    def link_memories(
        self,
        agent_uuid: str,
        source_memory_id: int,
        target_memory_id: int,
        relation_type: str,
        *,
        similarity_score: float | None = None,
    ) -> dict[str, Any]:
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
        return r.json()

    def list_memories(
        self,
        agent_uuid: str,
        *,
        memory_type: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if memory_type:
            params["memory_type"] = memory_type
        if category:
            params["category"] = category
        r = self._client.get(f"/api/v1/agents/{agent_uuid}/memories", params=params)
        r.raise_for_status()
        return _extract_list(r.json())
