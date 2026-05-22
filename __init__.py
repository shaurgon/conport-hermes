"""ConPort memory provider for Hermes Agent.

Implements `agent.memory_provider.MemoryProvider`. Synchronous per Hermes contract.
Plugin entry-point: `register(ctx)` (see pyproject.toml [project.entry-points."hermes_agent.plugins"]).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from .client import ConPortClient
from .models import IdentityFile, ProviderConfig
from .tools import TOOL_SCHEMAS, dispatch_tool

__version__ = "1.2.0"

PROVIDER_NAME = "conport"


_SYSTEM_PROMPT_BLOCK = """\
## ConPort — Agent Memory v2

Your persistent memory is a **tree**, not a flat list (decisions 660–682).
Identity is already bound; the init payload (trunk roots, active branches,
pending lift/conflict counts) is auto-fetched at session start and a
composite-scored recall is auto-injected before every turn.

> Project tools (decisions, tasks, documents, search) are intentionally
> **not** here: the agent layer is structurally separate from project
> memory (decision-660). For project work use the `conport` skill or
> direct REST against `/api/v1/...` — not this provider.

### Anatomy

- **trunk_root** + three reserved sub-stores: `identity_root` (who you
  are), `principles_root` (rules you follow), `person_knowledge_root`
  (facts about the user / world).
- **branches** — episodic threads off trunk_root. One per long-running
  task / topic. Origins ripen via gravity (decision-662) and can
  crystallize into **skills** (decision-663).
- **skills** — crystallized capabilities. Get cross-loaded
  (`agent_load_skill`) across branches; cross-branch reuse promotes
  them onto the trunk (decision-671).

### The loop

Three kinds of nodes (doc-91 §2.3): **experience** — tail nodes,
substrate that accumulates freely; **artifacts** — curated outputs
you synthesise from multiple experience nodes, the deliverable;
**skills** — frozen mature origins that emerge passively over many
cycles via gravity.

Task loop:

1. `agent_recall(task_query)` first — not `agent_remember`. Composite
   score finds relevant nodes across the whole tree.
2. Walk the branch from the hit. Off-theme child or semantic
   neighbour in another branch = signal — chase it via
   `agent_recall` on the fragment.
3. Write tails freely. Each new fact, observation, intermediate
   conclusion = one tail. **Don't pre-synthesize into a mega-node** —
   that starves gravity of signal. Tails are substrate.
4. When accumulated experience answers the task, emit the artifact:
   `agent_emit_artifact(branch_id, type, payload, derived_from=[…])`
   pulling from the experience nodes (across branches if needed)
   that contributed. The artifact IS the deliverable.
5. Skill crystallization is the long game, not per-task — origins
   ripen passively. Don't force it.

### Writes — classify, then `agent_remember`

Argmax routing is fast but memoryless about intent — across the trunk
it silently dumps everything into the largest cluster (usually
`person_knowledge_root`). Before each `agent_remember`, decide between
the two kinds of containers:

- **Trunk sub-stores** (always-loaded): `identity_root` (who I am),
  `principles_root` (declarative rules), `person_knowledge_root`
  (stable facts about user/world).
- **Branches** (contextual): one per task / topic / research theme.
  Created via `agent_create_branch` or emergently when
  `routing.decision='new_branch'`.

There is no third level of trunk sub-store. Anything that doesn't fit
one of the three belongs in a branch.

Decision tree:

| Question | Action |
|---|---|
| Self-statement / persona fact? | `agent_remember(content, parent_id=identity_root_id)` |
| Declarative cross-context rule or pitfall? | `parent_id=principles_root_id` |
| Stable fact about the user / world? | `parent_id=person_knowledge_root_id` |
| Tied to the current active task / thread? | `parent_id=active_branch_id` — let argmax place within it |
| New topic with no existing branch? | `agent_create_branch(name, anchor=trunk_root_id)` first, then write with the new id |

Research papers, debug chronicles, tool history — all of these
belong in **branches**, not in `person_knowledge_root`. Use one
branch per research theme (`research:agent-memory`,
`research:mcp-security`); each paper becomes a child of that origin
and gravity may eventually crystallize a synthesis skill.

`routing.decision='uncertain'` with cross-container alternatives
means the classification was off — re-call with the correct
`parent_id`. Inside the right container, accept argmax without
overriding.

### Trunk normalization sweep

Every N consolidation cycles (or once a week), walk
`person_knowledge_root` direct children with `agent_walk_branch` and
re-classify anything that is not a genuine fact about the user/world:

- Declarative rule → move to `principles_root`.
- Persona/self-fact → move to `identity_root`.
- Episodic content (research, debug log, tool chronicle) → find or
  create the appropriate branch, re-write there. Supersede the
  original under `person_knowledge_root`.

Same audit for `identity_root` and `principles_root` if they
accumulated unrelated content. The goal is on-theme content per
sub-store; episodic stuff lives in branches.

### Reads

- `agent_recall(query)` — composite-scored search across your whole
  tree. Pass `scope_root_id` to narrow to one sub-store.
- `agent_get_node(node_id)` / `agent_walk_branch(branch_id)` — explicit
  navigation when you already know the anchor.
- `agent_list_branches(state)` — what's active right now.

### Reflection

- `agent_reflect(node_id, new_content)` — manual gravity. Pass the
  merged content; backend re-embeds + runs consolidation +
  crystallisation checks. Backend never synthesises — you provide the
  merge (decision-692).

### Cross-pollination + promotion

When you see `pending_lift_candidates` in `agent_init`:
1. `agent_review_lift_candidates` → matched origins + scores
2. `agent_confirm_lift(candidate_id, action='accept', synthesized_content=..., target_trunk_parent_id=...)`

When you see `pending_promotion_conflicts`:
1. `agent_review_promotion_conflicts` → conflict skill + nearest trunk neighbours
2. `agent_resolve_promotion_conflict(skill_id, action='promote' | 'revert')`

### NEVER store

Secrets, passwords, API keys, tokens — even partially. Reference where
the value lives (`$API_KEY` env var) instead.

### Quality

1. Extract the insight, not the story. Bad: "Task X completed: did Y,
   then Z." Good: "POST /api/agents/{id}/skills/sync — `desiredSkills`
   defaults to null, must be passed explicitly."
2. Don't pre-search. Routing picks the right parent + gravity
   consolidates duplicates with `consolidation_count`. Just write.
3. Don't try to delete. Memory is non-destructive by design
   (decision-667); supersession happens via consolidation +
   re-crystallisation, not `forget`.

### Sunset (no v2 equivalent)

`conport_forget` and explicit `conport_link_memories` are gone.
Non-destructive gravity replaces the first; tree edges + trunk
promotion replace the second.

### Checklist

- Task arrived? First move = `agent_recall`, not `agent_remember`?
- Walked the branch + chased any off-theme child / semantic neighbour?
- Tails written freely (substrate) without forcing pre-synthesis?
- Task answer emitted via `agent_emit_artifact` with `derived_from=[…]`?
- Classified the content as trunk sub-store OR branch before remembering?
- New research / debug / chronicle theme → `agent_create_branch` instead of writing under `person_knowledge_root`?
- No secrets in the content?
- `pending_lift_candidates` > 0 → review queue?
- `pending_promotion_conflicts` > 0 → resolve them?
- Trunk normalization sweep run in the last N cycles?
"""


def _read_api_key_from_env_file(hermes_home: str) -> str | None:
    """Read CONPORT_API_KEY from $HERMES_HOME/.env in case the wizard
    just wrote it but our process env hasn't been refreshed yet."""
    env_path = Path(hermes_home) / ".env"
    if not env_path.exists():
        return None
    try:
        for line in env_path.read_text().splitlines():
            if line.startswith("CONPORT_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    except OSError:
        return None
    return None
DEFAULT_API_BASE = "https://api.conport.app"
IDENTITY_FILENAME = "conport.json"
PROVIDER_CONFIG_FILENAME = "conport_provider.json"


class ConPortMemoryProvider:
    """ConPort-backed long-term memory for Hermes agents."""

    def __init__(self) -> None:
        self._client: ConPortClient | None = None
        self._session_id: str | None = None
        self._hermes_home: str | None = None
        self._agent_uuid: str | None = None
        self._agent_context: str = "primary"
        self._agent_identity: str | None = None
        self._platform: str | None = None
        self._recall_limit: int = 5
        self._recall_timeout: float = 2.0
        # Cached agent_init payload (decision-681). Populated in initialize()
        # so prefetch / handle_tool_call can read trunk-root ids without a
        # second round-trip per turn.
        self._init_payload: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def is_available(self) -> bool:
        return bool(os.environ.get("CONPORT_API_KEY"))

    def get_config_schema(self) -> list[dict[str, Any]]:
        # Only api_key is user-configurable. Other settings (base URL,
        # recall limit/timeout) are code defaults and can still be
        # overridden by hand in $HERMES_HOME/conport_provider.json for
        # self-hosted instances or tuning, but they don't belong in the
        # setup wizard.
        return [
            {
                "key": "api_key",
                "secret": True,
                "env_var": "CONPORT_API_KEY",
                "required": True,
                "description": "ConPort API key (cport_live_...). Create one at https://conport.app.",
            },
        ]

    def save_config(self, values: dict[str, Any], hermes_home: str) -> None:
        """Persist non-secret config and auto-bootstrap identity.

        Hermes calls this after the schema wizard has already saved the API
        key to ``$HERMES_HOME/.env``. We finish the job by creating a default
        ConPort agent (one-shot, idempotent) so the user doesn't need to run
        ``hermes conport-hermes init`` separately. They still can, to rebind to a
        different agent.
        """
        non_secret = {k: v for k, v in values.items() if k != "api_key"}
        path = Path(hermes_home) / PROVIDER_CONFIG_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(non_secret, indent=2, ensure_ascii=False))
        self._bootstrap_identity_if_missing(hermes_home)

    def _bootstrap_identity_if_missing(self, hermes_home: str) -> None:
        identity_file = Path(hermes_home) / IDENTITY_FILENAME
        if identity_file.exists():
            return
        api_key = os.environ.get("CONPORT_API_KEY") or _read_api_key_from_env_file(hermes_home)
        if not api_key:
            print(
                "  Note: ConPort API key not found yet — run `hermes conport-hermes init` "
                "after the wizard finishes."
            )
            return
        from .setup_wizard import _create_agent, _save

        import socket
        agent_name = f"hermes-{socket.gethostname()}"
        try:
            agent = _create_agent(DEFAULT_API_BASE, api_key, agent_name)
        except Exception as e:  # noqa: BLE001 — don't crash the wizard
            print(f"  Note: ConPort agent auto-create failed ({e}); run `hermes conport-hermes init`.")
            return
        agent_uuid = agent.get("uuid") or agent.get("agent_uuid")
        if not agent_uuid:
            print("  Note: agent response missing uuid; run `hermes conport-hermes init`.")
            return
        identity: IdentityFile = {
            "agent_uuid": agent_uuid,
            "agent_name": agent.get("name", agent_name),
        }
        _save(hermes_home, identity)
        print(f"  Bound to ConPort agent: {identity['agent_name']} ({identity['agent_uuid']})")

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        """Hermes runtime context arrives via kwargs (run_agent.py:1705).

        We capture: hermes_home (storage scope), agent_context (writes-allowed
        gate), agent_identity (profile name), platform (origin tag).
        Other kwargs (user_id, chat_id, ...) are accepted but unused in v1.0.

        After loading config + identity we fire ``agent_init`` once per
        session (decision-681) to materialise the tree if this is a new
        agent and to refresh the cached trunk-root ids used by recall
        scoping. Failures here are non-fatal — Hermes still gets the
        tool surface; the agent will hit the backend on the first
        explicit call.
        """
        self._session_id = session_id
        self._hermes_home = kwargs.get("hermes_home") or os.environ.get(
            "HERMES_HOME", os.path.expanduser("~/.hermes")
        )
        self._agent_context = kwargs.get("agent_context") or "primary"
        self._agent_identity = kwargs.get("agent_identity")
        self._platform = kwargs.get("platform") or "cli"

        api_key = os.environ.get("CONPORT_API_KEY")
        if not api_key:
            return  # is_available() should have prevented activation; bail out safely.

        cfg = self._load_provider_config()
        self._recall_limit = int(cfg.get("recall_limit", 5))
        self._recall_timeout = float(cfg.get("recall_timeout_seconds", 2))
        base_url = cfg.get("api_base_url", DEFAULT_API_BASE)

        self._client = ConPortClient(base_url=base_url, api_key=api_key)
        self._agent_uuid = self._load_agent_uuid()

        if self._client and self._agent_uuid:
            try:
                # AgentInitPayload is a TypedDict; we store it as a plain
                # dict for forward-compat (server may add keys we don't
                # yet type) and to keep the union narrow.
                payload = self._client.agent_init(self._agent_uuid)
                self._init_payload = cast(dict[str, Any], payload)
            except Exception:  # noqa: BLE001 — bootstrap is best-effort
                self._init_payload = None
        else:
            self._init_payload = None

    def _load_provider_config(self) -> ProviderConfig:
        if not self._hermes_home:
            return {}
        p = Path(self._hermes_home) / PROVIDER_CONFIG_FILENAME
        if not p.exists():
            return {}
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        return cast(ProviderConfig, data) if isinstance(data, dict) else {}

    def _load_agent_uuid(self) -> str | None:
        if not self._hermes_home:
            return None
        p = Path(self._hermes_home) / IDENTITY_FILENAME
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        identity = cast(IdentityFile, data)
        uuid = identity.get("agent_uuid")
        return uuid if isinstance(uuid, str) else None

    # --- tool surface (per MemoryProvider contract) ---

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        # Always return the full schema list. Hermes collects schemas during
        # add_provider() — BEFORE initialize() runs — to build its tool
        # registry; a conditional gate here makes the tools invisible to the
        # LLM ("Unknown tool"). The not-initialized case is handled in
        # handle_tool_call.
        return list(TOOL_SCHEMAS)

    def handle_tool_call(self, name: str, args: dict[str, Any]) -> str:
        if not (self._client and self._agent_uuid):
            return json.dumps(
                {
                    "error": (
                        "ConPort provider not initialized — no identity. "
                        "Run `hermes conport-hermes init`."
                    )
                },
                ensure_ascii=False,
            )
        return dispatch_tool(
            tool_name=name,
            args=args,
            client=self._client,
            agent_uuid=self._agent_uuid,
        )

    # --- optional hooks ---

    def system_prompt_block(self) -> str | None:
        if not self._agent_uuid:
            return None
        return _SYSTEM_PROMPT_BLOCK

    def prefetch(self, query: str, **_kwargs: Any) -> str | None:
        if not (self._client and self._agent_uuid):
            return None
        try:
            hits = self._client.recall(
                agent_uuid=self._agent_uuid,
                query=query,
                limit=self._recall_limit,
                timeout=self._recall_timeout,
            )
        except Exception:  # noqa: BLE001 — non-blocking is required
            return None
        if not hits:
            return None
        lines: list[str] = []
        for h in hits:
            # RecallHit has id / content / similarity / composite_score
            # (the last one is the canonical sort key, decision-678).
            score = h.get("composite_score")
            if score is None:
                score = h.get("similarity")
            prefix = f"- (#{h.get('id', '?')}" + (f", {score:.2f}" if isinstance(score, (int, float)) else "") + ")"
            lines.append(f"{prefix} {h.get('content', '')}")
        return "Relevant ConPort memories:\n" + "\n".join(lines)

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        **_kwargs: Any,
    ) -> None:
        # Accept and ignore extra Hermes runtime kwargs (e.g. session_id
        # introduced in newer ABC revisions). No implicit writes — agent uses
        # explicit conport_remember tool.
        return None

    def on_session_end(self, messages: list[dict[str, Any]], **_kwargs: Any) -> None:
        return None

    def shutdown(self) -> None:
        if self._client:
            self._client.close()
            self._client = None


def register(ctx: Any) -> None:
    """Hermes calls this on plugin load.

    CLI subcommands (``hermes conport-hermes <cmd>``) live in cli.py and
    are discovered separately via plugins.memory.discover_plugin_cli_commands;
    not registered here.
    """
    ctx.register_memory_provider(ConPortMemoryProvider())


__all__ = ["ConPortMemoryProvider", "register", "__version__"]
