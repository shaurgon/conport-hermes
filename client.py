"""Synchronous REST client for the ConPort Agent Intent-API (v4) — doc-101.

The agent works with **intent verbs** (create_kind / get_kind / remember /
event / recall); ConPort owns storage. This client wraps the ``/memory/*``
intent endpoints plus a few aux operations the verbs don't cover (chat-turn,
extract-thread, subgraph, entity delete, event timeline, runs). Auth via Bearer
cport_live_… token.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar, cast

import httpx

from .models import AgentInitPayload, AgentRecord, KindInfo, RecallHit

_T = TypeVar("_T")


def _provider_version() -> str | None:
    """The running provider's version — ``__version__`` from this package.

    NOT ``importlib.metadata``: in the real Hermes deployment the plugin is a
    flat file layout (sync copies ``conport_hermes/`` to the plugin root, no
    pyproject / dist-info), so metadata lookup raises and we'd report nothing.
    ``__version__`` ships inside ``__init__.py`` and is the single source the
    bump keeps in lockstep with plugin.yaml. Lazy import dodges the circular
    dependency (``__init__`` imports this module). Sent to agent_init so the
    backend returns skill_update_available — the agent never hand-compares
    (decision-808).
    """
    try:
        from . import __version__
        return __version__
    except Exception:  # pragma: no cover — defensive
        return None


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
    """REST client for the v4 intent surface (``/memory/*``) + aux."""

    def __init__(self, base_url: str, api_key: str, *, default_timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        user_agent = f"conport-hermes/{_provider_version() or 'unknown'}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": user_agent},
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
        r = self._client.post("/api/v1/memory/init", json={
            "agent_uuid": agent_uuid,
            "skill_id": "conport-hermes",
            "skill_version": _provider_version(),
            "client_type": "hermes",
        })
        r.raise_for_status()
        return _as(AgentInitPayload, r.json())

    # ── Intent: structured domains (kinds) ───────────────────────────

    def create_kind(
        self, agent_uuid: str, name: str, fields: list[str],
        statuses: list[str] | None = None,
        refs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # ``refs`` values are either the legacy scalar ``target_kind`` or the
        # array form ``{"kind": target_kind, "multi": true}`` (decision-852).
        # No client-side validation — the server owns it; we forward verbatim.
        body: dict[str, Any] = {"agent_uuid": agent_uuid, "name": name, "fields": fields}
        if statuses:
            body["statuses"] = statuses
        if refs:
            body["refs"] = refs
        r = self._client.post("/api/v1/memory/create-kind", json=body)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def get_referrers(self, kind: str, name: str) -> list[dict[str, Any]]:
        """Items whose declared ref points at (kind, name) — owner-scoped server-side."""
        r = self._client.get("/api/v1/memory/referrers", params={"kind": kind, "name": name})
        r.raise_for_status()
        return _list_under(r.json(), "referrers")

    def get_kind(self, agent_uuid: str, name: str) -> KindInfo | None:
        # agent_uuid is accepted for surface symmetry; the REST endpoint scopes
        # by the authenticated owner, not the agent.
        r = self._client.get("/api/v1/memory/kind", params={"name": name})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return _as(KindInfo, r.json())

    # ── Intent: remember (free cognition OR structured item) ──────────

    def remember(
        self, agent_uuid: str, content: str | None = None, *,
        meta_type: str | None = None, visibility: str | None = None,
        edges: list[dict[str, Any]] | None = None,
        kind: str | None = None, name: str | None = None,
        fields: dict[str, Any] | None = None,
        relevant_until: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Dual-mode. ``kind`` set → structured item (kind/name/fields); else →
        free cognition node (content + optional meta_type/visibility/edges).
        ``relevant_until`` (ISO 8601) applies to either path — a validity
        horizon past which the memory drops in recall rank (never deleted).
        Routing happens server-side; this just forwards the right keys."""
        body: dict[str, Any] = {"agent_uuid": agent_uuid}
        if kind is not None:
            body["kind"] = kind
            if name is not None:
                body["name"] = name
            if fields is not None:
                body["fields"] = fields
        else:
            body["content"] = content
            if meta_type:
                body["meta_type"] = meta_type
            if visibility:
                body["visibility"] = visibility
            if edges:
                body["edges"] = edges
        if relevant_until:
            body["relevant_until"] = relevant_until
        r = self._client.post("/api/v1/memory/remember", json=body,
                              timeout=timeout or self._client.timeout)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # ── Intent: link (edge between two existing cognition nodes) ───────

    def link(
        self, agent_uuid: str, from_node_id: int, to_node_id: int,
        edge_type: str, properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Assert an explicit edge between two EXISTING cognition nodes.
        New nodes auto-link by meaning and remember(edges=…) covers
        new→existing; this covers the existing→existing case. ``edge_type`` is
        one of the 12 vocab types (6 structural: semantic/derived_from/temporal/
        skill_of/competing_view/supersedes — 6 domain: unifies/introduces/cites/
        uses_method/reports_finding/refines); the server validates it.
        ``properties`` is optional edge metadata (confidence in 0..1,
        source_item, evidence_section, note; unknown keys allowed)."""
        body: dict[str, Any] = {
            "agent_uuid": agent_uuid, "from_node_id": from_node_id,
            "to_node_id": to_node_id, "edge_type": edge_type,
        }
        if properties:
            body["properties"] = properties
        r = self._client.post("/api/v1/memory/link", json=body)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # ── Intent: event (change on a structured item) ───────────────────

    def event(
        self, agent_uuid: str, kind: str, name: str, note: str, *,
        fields: dict[str, Any] | None = None, event_type: str = "note",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "agent_uuid": agent_uuid, "kind": kind, "name": name, "note": note,
            "event_type": event_type,
        }
        if fields:
            body["fields"] = fields
        r = self._client.post("/api/v1/memory/event", json=body)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # ── Intent: recall (one ranked typed list) ────────────────────────

    def recall(
        self, agent_uuid: str, query: str, *, limit: int = 10,
        scope: dict[str, Any] | None = None, intent: str | None = None,
        timeout: float | None = None,
    ) -> list[RecallHit]:
        params: dict[str, Any] = {"q": query, "limit": limit, "agent_uuid": agent_uuid}
        if scope:
            params["scope"] = json.dumps(scope)
        if intent:
            params["intent"] = intent
        r = self._client.get("/api/v1/memory/recall", params=params,
                             timeout=timeout or self._client.timeout)
        r.raise_for_status()
        # v4 recall returns a typed list under "results" (node|item); "nodes" is
        # a back-compat subset. Prefer results.
        return cast(list[RecallHit], _list_under(r.json(), "results", "nodes"))

    # ── Aux: conversation intake ──────────────────────────────────────

    def chat_turn(self, agent_uuid: str, role: str, text: str) -> dict[str, Any]:
        r = self._client.post("/api/v1/memory/chat-turn",
                              json={"agent_uuid": agent_uuid, "role": role, "text": text})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def extract_thread(self, agent_uuid: str, message_ids: list[int]) -> dict[str, Any]:
        r = self._client.post("/api/v1/memory/extract-thread",
                              json={"agent_uuid": agent_uuid, "message_ids": message_ids})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def extract_into(
        self, agent_uuid: str, item_id: int | None = None,
        nodes: list[dict[str, Any]] | None = None, *,
        edges: list[dict[str, Any]] | None = None,
        item_kind: str | None = None, item_name: str | None = None,
        source_entity_id: int | None = None,
    ) -> dict[str, Any]:
        """Batch-create agent-extracted nodes + edges under a source
        (decision-853 / decision-859 — pure storage, no backend LLM; the AGENT
        did the extraction). Each new node is auto-stamped ``derived_from`` the
        source.

        Source is EXACTLY ONE of (server validates ``invalid_source``):
        - a cognition NODE — ``item_id``; provenance is a ``derived_from``
          ``harness_edge``. Returns ``item_id`` + ``derived_from_created``.
        - a WORKSPACE ITEM — either the ``(item_kind, item_name)`` handle OR the
          raw ``source_entity_id``; provenance rides the node↔item link. Returns
          ``entity_id`` + ``entity_links_created``.

        ``nodes`` is a list of ``{content, meta_type?, visibility?}``. ``edges``
        reference the new nodes by index: ``{from_index, to_index, edge_type,
        properties?}`` between two new nodes, or ``{from_index, target_node_id,
        edge_type, properties?}`` to a pre-existing owned node. Returns
        ``{node_ids, nodes_created, edges_created, edge_errors?}`` plus the
        source-discriminated keys above."""
        body: dict[str, Any] = {"agent_uuid": agent_uuid, "nodes": nodes or []}
        if item_id is not None:
            body["item_id"] = item_id
        if item_kind is not None:
            body["item_kind"] = item_kind
        if item_name is not None:
            body["item_name"] = item_name
        if source_entity_id is not None:
            body["source_entity_id"] = source_entity_id
        if edges:
            body["edges"] = edges
        r = self._client.post("/api/v1/memory/extract-into", json=body)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    # ── Aux: explore + timeline + cleanup ─────────────────────────────

    def get_subgraph(self, agent_uuid: str, root_node_id: int, *, depth: int = 2) -> dict[str, Any]:
        r = self._client.get("/api/v1/memory/subgraph",
                             params={"agent_uuid": agent_uuid, "root_node_id": root_node_id, "depth": depth})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def graph_stats(self, agent_uuid: str) -> dict[str, Any]:
        r = self._client.get("/api/v1/memory/graph-stats",
                             params={"agent_uuid": agent_uuid})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def node_forget(self, agent_uuid: str, node_id: int) -> dict[str, Any]:
        """Soft-forget a cognition node — hidden from every read surface,
        row kept server-side. Irreversible from the agent surface."""
        r = self._client.post("/api/v1/memory/node-forget",
                              json={"agent_uuid": agent_uuid, "node_id": node_id})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def node_mute(self, agent_uuid: str, node_id: int) -> dict[str, Any]:
        """Per-viewer mute — hide a node from THIS agent's reads only.
        Reversible via node_unmute; the shared corpus is untouched."""
        r = self._client.post("/api/v1/memory/node-mute",
                              json={"agent_uuid": agent_uuid, "node_id": node_id})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def node_unmute(self, agent_uuid: str, node_id: int) -> dict[str, Any]:
        """Reverse a per-viewer mute — the node surfaces in reads again."""
        r = self._client.post("/api/v1/memory/node-unmute",
                              json={"agent_uuid": agent_uuid, "node_id": node_id})
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def entity_list(
        self, kind: str, attrs_filter: dict[str, Any] | None = None, *, limit: int = 50,
    ) -> dict[str, Any]:
        """List the members of a kind — exact, exhaustive, owner-scoped, ordered
        by name. Unlike recall (fuzzy/ranked) or get_referrers (inverse refs),
        this returns the actual items of the kind. ``attrs_filter`` is an optional
        jsonb subset match, forwarded JSON-encoded. Returns the raw
        ``{entities, total}`` dict from the server (limit clamped server-side to
        1..200)."""
        params: dict[str, Any] = {"entity_type": kind, "limit": limit}
        if attrs_filter is not None:
            params["attrs_filter"] = json.dumps(attrs_filter)
        r = self._client.get("/api/v1/workspace/entities", params=params)
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def _entity_get(self, kind: str, name: str) -> dict[str, Any] | None:
        """Resolve a structured item to its row (internal — for entity_delete).

        Max page (server caps limit at 200): this resolves an exact (kind, name);
        the server lists ORDER BY name, so a small default page could miss a
        late-sorting name."""
        r = self._client.get(
            "/api/v1/workspace/entities",
            params={"entity_type": kind, "limit": 200},
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        entities = _list_under(r.json(), "entities")
        return next((e for e in entities if e.get("name") == name), None)

    def entity_delete(self, kind: str, name: str) -> dict[str, Any]:
        """Delete a structured item (+ its events) by (kind, name) — fix a mistake."""
        ent = self._entity_get(kind, name)
        if not ent:
            return {"deleted": False, "error": "not_found"}
        r = self._client.delete(f"/api/v1/workspace/entities/{ent['id']}")
        if r.status_code == 404:  # raced with another delete — already gone
            return {"deleted": False, "error": "not_found"}
        r.raise_for_status()
        return cast(dict[str, Any], r.json())

    def event_query(self, *, entity_id: int | None = None, event_type: str | None = None,
                    run_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Read an item's timeline (events aren't in recall). Pass the item_id
        from a recall result as ``entity_id``."""
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

    # ── Aux: run (skill-execution tracking) ───────────────────────────

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
