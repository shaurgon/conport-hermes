"""Synchronous REST client for the ConPort Agent Memory v2 surface.

Wraps every endpoint a Hermes agent needs to drive its tree-shaped memory
(decisions 660–682, doc-91 §8). Auth is ``Authorization: Bearer cport_live_…``;
``X-API-Key`` works too thanks to the MCP-mount translator middleware
(decision-718), but Bearer is the canonical path the REST API expects.

Method names match the corresponding ``agent_*`` MCP tool — keeps the
mental model identical when you switch between plugin and direct MCP
access.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

import httpx

from .models import (
    AgentInitPayload,
    AgentNodeResponse,
    AgentRecord,
    BranchSummary,
    RecallHit,
)

_T = TypeVar("_T")


def _list_under(data: object, *keys: str) -> list[dict[str, Any]]:
    """Pull the first matching list from a response envelope.

    ConPort v2 endpoints wrap arrays under semantic keys (``branches``,
    ``candidates``, ``conflicts``, ``versions``, ``notes``, …). When the
    server returns a bare list we accept that too.
    """
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
        raise TypeError(
            f"Expected JSON object for {record_type.__name__}, "
            f"got {type(payload).__name__}"
        )
    return cast(_T, payload)


class ConPortClient:
    """Thin httpx wrapper. One method per agent_* tool / REST endpoint.

    Reused by both the LLM-facing tool dispatcher (``tools.py``) and the
    lifecycle hooks on ``ConPortMemoryProvider`` (``__init__.py``).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        default_timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "conport-hermes/1.0.0",
            },
            timeout=default_timeout,
        )

    def close(self) -> None:
        self._client.close()

    # --- agent identity ---

    def get_agent(self, agent_uuid: str) -> AgentRecord:
        r = self._client.get(f"/api/v1/agents/{agent_uuid}")
        r.raise_for_status()
        return _as(AgentRecord, r.json())

    def create_agent(self, name: str, *, agent_type: str = "worker") -> AgentRecord:
        r = self._client.post("/api/v1/agents", json={"name": name, "type": agent_type})
        r.raise_for_status()
        return _as(AgentRecord, r.json())

    def agent_init(self, agent_uuid: str) -> AgentInitPayload:
        """Bootstrap or load. Returns the init payload (decision-681).

        First call for a new agent creates trunk + the 3 reserved sub-store
        roots (identity / principles / person_knowledge). Subsequent calls
        return ``bootstrap_state='continuing'`` with the existing tree.
        """
        r = self._client.post(f"/api/v1/agents/{agent_uuid}/init")
        r.raise_for_status()
        return _as(AgentInitPayload, r.json())

    # --- tree navigation ---

    def get_node(self, agent_uuid: str, node_id: int) -> AgentNodeResponse:
        r = self._client.get(f"/api/v1/agents/{agent_uuid}/nodes/{node_id}")
        r.raise_for_status()
        return _as(AgentNodeResponse, r.json())

    def list_branches(
        self, agent_uuid: str, *, state: str | None = None
    ) -> list[BranchSummary]:
        params: dict[str, Any] = {}
        if state:
            params["state"] = state
        r = self._client.get(f"/api/v1/agents/{agent_uuid}/branches", params=params)
        r.raise_for_status()
        return cast(list[BranchSummary], _list_under(r.json(), "branches"))

    def walk_branch(self, agent_uuid: str, branch_id: int) -> dict[str, Any]:
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/branches/{branch_id}/walk"
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # --- memory write/read ---

    def remember(
        self,
        agent_uuid: str,
        content: str,
        *,
        parent_id: int | None = None,
        branch_id: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """v2 write with argmax routing (decision-673).

        ``parent_id`` left as ``None`` lets the backend pick the best
        ancestor via embedding similarity — the recommended path. Pass
        an explicit ``parent_id`` (e.g. ``identity_root_id``) only when
        you specifically want to anchor the write.
        """
        payload: dict[str, Any] = {"content": content}
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if branch_id is not None:
            payload["branch_id"] = branch_id
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/memories/v2",
            json=payload,
            timeout=timeout if timeout is not None else self._client.timeout,
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def recall(
        self,
        agent_uuid: str,
        query: str,
        *,
        scope_root_id: int | None = None,
        limit: int = 10,
        offset: int = 0,
        timeout: float | None = None,
    ) -> list[RecallHit]:
        """v2 recall with composite scoring (decision-678).

        score = 0.6 · cosine + 0.2 · recall_factor + 0.2 · foundational_boost.
        ``scope_root_id`` lets you narrow the search to one sub-tree (e.g.
        only ``person_knowledge_root_id`` for biographical recall).
        """
        params: dict[str, Any] = {"q": query, "limit": limit, "offset": offset}
        if scope_root_id is not None:
            params["scope_root_id"] = scope_root_id
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/memories/recall/v2",
            params=params,
            timeout=timeout if timeout is not None else self._client.timeout,
        )
        r.raise_for_status()
        return cast(list[RecallHit], _list_under(r.json(), "results"))

    def reflect(
        self,
        agent_uuid: str,
        node_id: int,
        *,
        new_content: str | None = None,
    ) -> dict[str, Any]:
        """Manual gravity invoke (decision-667 / decision-692).

        ``new_content`` provided → backend persists merged content + refreshes
        embedding before running consolidation/crystallization passes.
        Omitted → pure bookkeeping (recompute counters, maybe emerge a skill).
        Backend never synthesises; the agent has done the merge upstream.
        """
        body: dict[str, Any] = {}
        if new_content is not None:
            body["new_content"] = new_content
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/reflect/v2",
            params={"node_id": node_id},
            json=body,
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # --- branch lifecycle ---

    def create_branch(
        self,
        agent_uuid: str,
        name: str,
        *,
        anchor_id: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if anchor_id is not None:
            body["anchor_id"] = anchor_id
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/branches/create", json=body
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def close_branch(
        self,
        agent_uuid: str,
        branch_id: int,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if reason is not None:
            body["reason"] = reason
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/branches/{branch_id}/close",
            json=body,
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def activate_node(self, agent_uuid: str, node_id: int) -> dict[str, Any]:
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/nodes/{node_id}/activate"
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def activate_branch(self, agent_uuid: str, branch_id: int) -> dict[str, Any]:
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/branches/{branch_id}/activate"
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # --- artifacts ---

    def emit_artifact(
        self,
        agent_uuid: str,
        *,
        artifact_type: str,
        payload: str | None = None,
        external_url: str | None = None,
        branch_id: int | None = None,
        derived_from: list[int] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"artifact_type": artifact_type}
        if payload is not None:
            body["payload"] = payload
        if external_url is not None:
            body["external_url"] = external_url
        if branch_id is not None:
            body["branch_id"] = branch_id
        if derived_from is not None:
            body["derived_from"] = derived_from
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/artifacts", json=body
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def list_artifacts(
        self,
        agent_uuid: str,
        *,
        branch_id: int | None = None,
        artifact_type: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if branch_id is not None:
            params["branch_id"] = branch_id
        if artifact_type is not None:
            params["artifact_type"] = artifact_type
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/artifacts", params=params
        )
        r.raise_for_status()
        return _list_under(r.json(), "artifacts")

    def get_artifact(self, agent_uuid: str, artifact_id: int) -> dict[str, Any]:
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/artifacts/{artifact_id}"
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def artifact_provenance(
        self, agent_uuid: str, artifact_id: int
    ) -> dict[str, Any]:
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/artifacts/{artifact_id}/provenance"
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def node_artifacts(self, agent_uuid: str, node_id: int) -> list[dict[str, Any]]:
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/nodes/{node_id}/artifacts"
        )
        r.raise_for_status()
        return _list_under(r.json(), "artifacts")

    # --- lift candidates (cross-pollination) ---

    def list_lift_candidates(self, agent_uuid: str) -> list[dict[str, Any]]:
        r = self._client.get(f"/api/v1/agents/{agent_uuid}/lift-candidates")
        r.raise_for_status()
        return _list_under(r.json(), "candidates")

    def confirm_lift(
        self,
        agent_uuid: str,
        candidate_id: int,
        action: str,
        *,
        synthesized_content: str | None = None,
        target_trunk_parent_id: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"action": action}
        if synthesized_content is not None:
            body["synthesized_content"] = synthesized_content
        if target_trunk_parent_id is not None:
            body["target_trunk_parent_id"] = target_trunk_parent_id
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/lift-candidates/{candidate_id}/confirm",
            json=body,
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def request_synthesis_assistance(
        self, agent_uuid: str, candidate_id: int
    ) -> dict[str, Any]:
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/lift-candidates/{candidate_id}/synthesis-assistance"
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # --- promotion conflicts ---

    def list_promotion_conflicts(self, agent_uuid: str) -> list[dict[str, Any]]:
        r = self._client.get(f"/api/v1/agents/{agent_uuid}/promotion-conflicts")
        r.raise_for_status()
        return _list_under(r.json(), "conflicts")

    def resolve_promotion_conflict(
        self, agent_uuid: str, skill_id: int, action: str
    ) -> dict[str, Any]:
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/skills/{skill_id}/resolve-promotion",
            json={"action": action},
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # --- skills (versioning + notes + activation log) ---

    def load_skill(self, agent_uuid: str, skill_id: int) -> dict[str, Any]:
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/skills/{skill_id}/load"
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def list_skills(self, agent_uuid: str) -> list[dict[str, Any]]:
        r = self._client.get(f"/api/v1/agents/{agent_uuid}/skills")
        r.raise_for_status()
        return _list_under(r.json(), "skills")

    def skill_versions(self, agent_uuid: str, skill_id: int) -> list[dict[str, Any]]:
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/skills/{skill_id}/versions"
        )
        r.raise_for_status()
        return _list_under(r.json(), "versions")

    def skill_version(
        self, agent_uuid: str, skill_id: int, version_number: int
    ) -> dict[str, Any]:
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/skills/{skill_id}/versions/{version_number}"
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def skill_md(self, agent_uuid: str, skill_id: int) -> str:
        r = self._client.get(f"/api/v1/agents/{agent_uuid}/skills/{skill_id}/md")
        r.raise_for_status()
        data = r.json()
        return cast(str, data.get("markdown", "")) if isinstance(data, dict) else ""

    def skill_notes(
        self,
        agent_uuid: str,
        skill_id: int,
        *,
        include_superseded: bool = False,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if include_superseded:
            params["include_superseded"] = "true"
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/skills/{skill_id}/notes",
            params=params,
        )
        r.raise_for_status()
        return _list_under(r.json(), "notes")

    def add_skill_note(
        self,
        agent_uuid: str,
        skill_id: int,
        content: str,
        note_type: str,
    ) -> dict[str, Any]:
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/skills/{skill_id}/notes",
            json={"content": content, "note_type": note_type},
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def supersede_skill_note(
        self, agent_uuid: str, note_id: int
    ) -> dict[str, Any]:
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/skill-notes/{note_id}/supersede"
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def complete_re_crystallization(
        self,
        agent_uuid: str,
        skill_id: int,
        new_content: str,
        *,
        integrated_note_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"new_content": new_content}
        if integrated_note_ids is not None:
            body["integrated_note_ids"] = integrated_note_ids
        r = self._client.post(
            f"/api/v1/agents/{agent_uuid}/skills/{skill_id}/re-crystallize",
            json=body,
        )
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def review_re_crystallization(self, agent_uuid: str) -> list[dict[str, Any]]:
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/re-crystallization-candidates"
        )
        r.raise_for_status()
        return _list_under(r.json(), "candidates")

    def skill_activations(
        self, agent_uuid: str, skill_id: int, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        r = self._client.get(
            f"/api/v1/agents/{agent_uuid}/skills/{skill_id}/activations",
            params={"limit": limit},
        )
        r.raise_for_status()
        return _list_under(r.json(), "activations")
