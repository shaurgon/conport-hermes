"""Synchronous REST client for ConPort Agent Memory (sphere graph) + Workspace.

Wraps every endpoint a Hermes agent needs. Auth via Bearer cport_live_… token.
Method names match MCP tool names for consistency.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

import httpx

from .models import AgentInitPayload, AgentRecord, RecallHit

_T = TypeVar("_T")


def _list_under(data: object, *keys: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for k in keys:
            v = data.get(k)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    return []


def _as(record_type: type[_T], payload: object) -> _T:
    if not isinstance(payload, dict):
        raise TypeError(f"Expected dict for {record_type.__name__}, got {type(payload).__name__}")
    return cast(_T, payload)


class ConPortClient:
    """REST client for v3 memory + workspace endpoints."""

    def __init__(self, base_url: str, api_key: str, *, default_timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "conport-hermes/2.0.0"},
            timeout=default_timeout,
        )

    def close(self) -> None:
        self._client.close()

    # ── Agent identity ───────────────────────────────────────────────

    def get_agent(self, agent_uuid: str) -> AgentRecord:
        r = self._client.get(f"/api/v1/agents/{agent_uuid}")
        r.raise_for_status()
        return _as(AgentRecord, r.json())

    def create_agent(self, name: str, *, agent_type: str = "worker") -> AgentRecord:
        r = self._client.post("/api/v1/agents", json={"name": name, "type": agent_type})
        r.raise_for_status()
        return _as(AgentRecord, r.json())

    def agent_init(self, agent_uuid: str) -> AgentInitPayload:
        r = self._client.get(f"/api/v1/agents/{agent_uuid}/graph")
        r.raise_for_status()
        return _as(AgentInitPayload, r.json())

    # ── Memory: write ────────────────────────────────────────────────

    def remember(
        self, agent_uuid: str, content: str, *,
        meta_type: str = "fact", visibility: str | None = None,
        edges: list[dict[str, Any]] | None = None, timeout: float | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"agent_uuid": agent_uuid, "meta_type": meta_type, "content": content}
        if visibility:
            body["visibility"] = visibility
        if edges:
            body["edges"] = edges
        r = self._client.post("/api/v1/agents/remember", json=body,
                              timeout=timeout or self._client.timeout)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def chat_turn(self, agent_uuid: str, role: str, text: str) -> dict[str, Any]:
        r = self._client.post("/api/v1/agents/chat-turn",
                              json={"agent_uuid": agent_uuid, "role": role, "text": text})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def extract_thread(self, agent_uuid: str, message_ids: list[int]) -> dict[str, Any]:
        r = self._client.post("/api/v1/agents/extract-thread",
                              json={"agent_uuid": agent_uuid, "message_ids": message_ids})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # ── Memory: read ─────────────────────────────────────────────────

    def recall(
        self, agent_uuid: str, query: str, *, limit: int = 10,
        scope: dict[str, Any] | None = None, timeout: float | None = None,
    ) -> list[RecallHit]:
        params: dict[str, Any] = {"q": query, "limit": limit, "agent_uuid": agent_uuid}
        if scope:
            params["scope"] = scope
        r = self._client.get("/api/v1/agents/recall", params=params,
                             timeout=timeout or self._client.timeout)
        r.raise_for_status()
        return cast(list[RecallHit], _list_under(r.json(), "nodes"))

    def get_subgraph(self, agent_uuid: str, root_node_id: int, *, depth: int = 2) -> dict[str, Any]:
        r = self._client.get("/api/v1/agents/subgraph",
                             params={"agent_uuid": agent_uuid, "root_node_id": root_node_id, "depth": depth})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # ── Workspace: entity ────────────────────────────────────────────

    def entity_upsert(
        self, agent_uuid: str, entity_type: str, name: str, attrs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"agent_uuid": agent_uuid, "entity_type": entity_type, "name": name}
        if attrs:
            body["attrs"] = attrs
        r = self._client.post("/api/v1/workspace/entities", json=body)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def entity_get(self, entity_type: str, name: str) -> dict[str, Any] | None:
        r = self._client.get("/api/v1/workspace/entities", params={"entity_type": entity_type})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        entities = _list_under(r.json(), "entities")
        return next((e for e in entities if e.get("name") == name), None)

    def entity_list(self, entity_type: str, *, limit: int = 50) -> list[dict[str, Any]]:
        r = self._client.get("/api/v1/workspace/entities", params={"entity_type": entity_type, "limit": limit})
        r.raise_for_status()
        return _list_under(r.json(), "entities")

    # ── Workspace: event ─────────────────────────────────────────────

    def event_record(
        self, agent_uuid: str, event_type: str, payload: dict[str, Any], *,
        entity_id: int | None = None, occurred_at: str | None = None, run_id: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"agent_uuid": agent_uuid, "event_type": event_type, "payload": payload}
        if entity_id is not None:
            body["entity_id"] = entity_id
        if occurred_at:
            body["occurred_at"] = occurred_at
        if run_id is not None:
            body["run_id"] = run_id
        r = self._client.post("/api/v1/workspace/events", json=body)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def event_query(self, *, entity_id: int | None = None, event_type: str | None = None,
                    run_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if entity_id is not None:
            params["entity_id"] = entity_id
        if event_type:
            params["event_type"] = event_type
        if run_id is not None:
            params["run_id"] = run_id
        r = self._client.get("/api/v1/workspace/events", params=params)
        r.raise_for_status()
        return _list_under(r.json(), "events")

    # ── Workspace: run ───────────────────────────────────────────────

    def run_start(self, agent_uuid: str, skill_name: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"agent_uuid": agent_uuid, "skill_name": skill_name}
        if params:
            body["params"] = params
        r = self._client.post("/api/v1/workspace/runs", json=body)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def run_finish(self, run_id: int, status: str, *, outputs: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"status": status}
        if outputs:
            body["outputs"] = outputs
        r = self._client.patch(f"/api/v1/workspace/runs/{run_id}", json=body)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # ── Workspace: projection ────────────────────────────────────────

    def projection_record(
        self, agent_uuid: str, entity_id: int, projection_type: str, value: dict[str, Any], *,
        derived_from_event_ids: list[int] | None = None, derived_from_run_id: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "agent_uuid": agent_uuid, "entity_id": entity_id,
            "projection_type": projection_type, "value": value,
        }
        if derived_from_event_ids:
            body["derived_from_event_ids"] = derived_from_event_ids
        if derived_from_run_id is not None:
            body["derived_from_run_id"] = derived_from_run_id
        r = self._client.post("/api/v1/workspace/projections", json=body)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def projection_current(self, entity_id: int, projection_type: str) -> dict[str, Any] | None:
        r = self._client.get("/api/v1/workspace/projections/current",
                             params={"entity_id": entity_id, "projection_type": projection_type})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def projection_history(self, entity_id: int, projection_type: str, *, limit: int = 100) -> list[dict[str, Any]]:
        r = self._client.get("/api/v1/workspace/projections/history",
                             params={"entity_id": entity_id, "projection_type": projection_type, "limit": limit})
        r.raise_for_status()
        return _list_under(r.json(), "projections")

    # ── Cross-link ───────────────────────────────────────────────────

    def link_node_to_entity(self, agent_uuid: str, node_id: int, entity_id: int,
                            link_type: str = "mentions") -> dict[str, Any]:
        r = self._client.post("/api/v1/workspace/node-entity-links",
                              json={"agent_uuid": agent_uuid, "node_id": node_id,
                                    "entity_id": entity_id, "link_type": link_type})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())
