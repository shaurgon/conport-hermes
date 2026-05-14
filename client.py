"""Synchronous REST client for the ConPort agent-memory API.

Auth: Bearer cport_live_… (decision D483: API key over OAuth for headless agents).
Endpoints follow https://api.conport.app/openapi.json.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

import httpx

from .models import (
    AgentRecord,
    DecisionRecord,
    DocumentRecord,
    MemoryLinkRecord,
    MemoryRecord,
    ProgressRecord,
    ProjectRecord,
    ReflectResult,
    SearchResultRecord,
    TaskRecord,
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
        timeout: float | None = None,
    ) -> list[MemoryRecord]:
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

    def reflect(self, agent_uuid: str, scope: str = "day") -> ReflectResult:
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/memories/reflect",
            params={"scope": scope},
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

    # --- projects ---

    def get_project(self, identifier: str | int) -> ProjectRecord:
        r = self._client.get(f"/api/v1/projects/{identifier}")
        r.raise_for_status()
        return _as(ProjectRecord, r.json())

    # --- search ---

    def search(
        self,
        query: str,
        *,
        project_id: int | None = None,
        limit: int = 20,
        item_types: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[SearchResultRecord]:
        payload: dict[str, Any] = {"query": query, "limit": limit}
        if project_id is not None:
            payload["project_id"] = project_id
        if item_types:
            payload["item_types"] = item_types
        if tags:
            payload["tags"] = tags
        r = self._client.post("/api/v1/search", json=payload)
        r.raise_for_status()
        return cast(list[SearchResultRecord], _extract_named_list(r.json(), "results"))

    # --- tasks ---

    def create_task(
        self,
        project_id: int,
        *,
        title: str,
        description: str | None = None,
        status: str = "TODO",
        priority: int = 3,
        parent_task_id: int | None = None,
    ) -> TaskRecord:
        payload: dict[str, Any] = {
            "title": title,
            "status": status,
            "priority": priority,
        }
        if description is not None:
            payload["description"] = description
        if parent_task_id is not None:
            payload["parent_task_id"] = parent_task_id
        r = self._client.post(f"/api/v1/projects/{project_id}/tasks", json=payload)
        r.raise_for_status()
        return _as(TaskRecord, r.json())

    def update_task(
        self,
        project_id: int,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        parent_task_id: int | None = None,
        resolution: str | None = None,
    ) -> TaskRecord:
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if priority is not None:
            payload["priority"] = priority
        if parent_task_id is not None:
            payload["parent_task_id"] = parent_task_id
        if resolution is not None:
            payload["resolution"] = resolution
        r = self._client.put(f"/api/v1/projects/{project_id}/tasks/{task_id}", json=payload)
        r.raise_for_status()
        return _as(TaskRecord, r.json())

    def list_tasks(
        self,
        project_id: int,
        *,
        status: str = "TODO,IN_PROGRESS",
        priority: int | None = None,
        limit: int = 50,
    ) -> list[TaskRecord]:
        params: dict[str, Any] = {"status": status, "limit": limit}
        if priority is not None:
            params["priority"] = priority
        r = self._client.get(f"/api/v1/projects/{project_id}/tasks", params=params)
        r.raise_for_status()
        return cast(list[TaskRecord], _extract_named_list(r.json(), "tasks"))

    # --- decisions ---

    def create_decision(
        self,
        project_id: int,
        *,
        summary: str,
        rationale: str | None = None,
        tags: list[str] | None = None,
    ) -> DecisionRecord:
        payload: dict[str, Any] = {"summary": summary, "tags": tags or []}
        if rationale is not None:
            payload["rationale"] = rationale
        r = self._client.post(f"/api/v1/projects/{project_id}/decisions", json=payload)
        r.raise_for_status()
        return _as(DecisionRecord, r.json())

    # --- progress ---

    def create_progress(
        self,
        project_id: int,
        *,
        description: str,
        title: str | None = None,
        parent_id: int | None = None,
        linked_item_type: str | None = None,
        linked_item_id: int | None = None,
    ) -> ProgressRecord:
        payload: dict[str, Any] = {"description": description}
        if title is not None:
            payload["title"] = title
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if linked_item_type is not None:
            payload["linked_item_type"] = linked_item_type
        if linked_item_id is not None:
            payload["linked_item_id"] = linked_item_id
        r = self._client.post(f"/api/v1/projects/{project_id}/progress", json=payload)
        r.raise_for_status()
        return _as(ProgressRecord, r.json())

    # --- documents ---

    def get_document(
        self, project_id: int, document_id: int, *, raw: bool = False
    ) -> DocumentRecord:
        params = {"raw": "true"} if raw else {}
        r = self._client.get(
            f"/api/v1/projects/{project_id}/documents/{document_id}", params=params
        )
        r.raise_for_status()
        return _as(DocumentRecord, r.json())

    def list_documents(
        self,
        project_id: int,
        *,
        doc_type: str | None = None,
        limit: int = 50,
    ) -> list[DocumentRecord]:
        params: dict[str, Any] = {"limit": limit}
        if doc_type:
            params["doc_type"] = doc_type
        r = self._client.get(f"/api/v1/projects/{project_id}/documents", params=params)
        r.raise_for_status()
        return cast(list[DocumentRecord], _extract_named_list(r.json(), "documents"))

    def create_document(
        self,
        project_id: int,
        *,
        title: str,
        content: str,
        doc_type: str = "spec",
        parent_document_id: int | None = None,
        author: str | None = None,
        external_url: str | None = None,
        tags: list[str] | None = None,
    ) -> DocumentRecord:
        payload: dict[str, Any] = {
            "title": title,
            "content": content,
            "doc_type": doc_type,
            "tags": tags or [],
        }
        if parent_document_id is not None:
            payload["parent_document_id"] = parent_document_id
        if author is not None:
            payload["author"] = author
        if external_url is not None:
            payload["external_url"] = external_url
        r = self._client.post(f"/api/v1/projects/{project_id}/documents", json=payload)
        r.raise_for_status()
        return _as(DocumentRecord, r.json())

    def update_document(
        self,
        project_id: int,
        document_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        doc_type: str | None = None,
        parent_document_id: int | None = None,
        author: str | None = None,
        external_url: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
    ) -> DocumentRecord:
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if content is not None:
            payload["content"] = content
        if doc_type is not None:
            payload["doc_type"] = doc_type
        if parent_document_id is not None:
            payload["parent_document_id"] = parent_document_id
        if author is not None:
            payload["author"] = author
        if external_url is not None:
            payload["external_url"] = external_url
        if tags is not None:
            payload["tags"] = tags
        if status is not None:
            payload["status"] = status
        r = self._client.put(
            f"/api/v1/projects/{project_id}/documents/{document_id}", json=payload
        )
        r.raise_for_status()
        return _as(DocumentRecord, r.json())

    # --- document blocks ---

    def get_block(
        self, project_id: int, document_id: int, block_ulid: str,
    ) -> dict[str, Any]:
        """Read a single block by ULID."""
        r = self._client.get(
            f"/api/v1/projects/{project_id}/documents/{document_id}/blocks/{block_ulid}"
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def update_block(
        self, project_id: int, document_id: int, block_ulid: str, markdown: str,
    ) -> dict[str, Any]:
        """Replace one block's markdown."""
        r = self._client.patch(
            f"/api/v1/projects/{project_id}/documents/{document_id}/blocks/{block_ulid}",
            json={"markdown": markdown},
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def insert_block(
        self,
        project_id: int,
        document_id: int,
        markdown: str,
        *,
        after: str | None = None,
        before: str | None = None,
    ) -> dict[str, Any]:
        """Insert a block. Pass after=<ulid> or before=<ulid> to position; default appends to end."""
        if after is not None and before is not None:
            raise ValueError("insert_block: pass at most one of after= or before=")
        payload: dict[str, Any] = {"markdown": markdown}
        if after is not None:
            payload["after"] = after
        if before is not None:
            payload["before"] = before
        r = self._client.post(
            f"/api/v1/projects/{project_id}/documents/{document_id}/blocks",
            json=payload,
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def delete_block(
        self, project_id: int, document_id: int, block_ulid: str,
    ) -> None:
        """Delete one block. Idempotent."""
        r = self._client.delete(
            f"/api/v1/projects/{project_id}/documents/{document_id}/blocks/{block_ulid}"
        )
        r.raise_for_status()
