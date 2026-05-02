"""ConPort memory provider for Hermes Agent.

Implements `agent.memory_provider.MemoryProvider`. Synchronous per Hermes contract.
Plugin entry-point: `register(ctx)` (see pyproject.toml [project.entry-points."hermes_agent.plugins"]).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .client import ConPortClient
from .tools import TOOL_SCHEMAS, dispatch_tool

__version__ = "0.1.7"

PROVIDER_NAME = "conport"


_SYSTEM_PROMPT_BLOCK = """\
## ConPort — Persistent Memory

ConPort is your long-term knowledge graph. Identity is already bound to this
profile; recall is auto-injected before every turn.

### NEVER store
- Secrets, passwords, API keys, tokens — even partially.
  Bad: "API key: 0a732108..."  Good: "API key is in $API_KEY env var"

### Quality
1. Extract the insight, not the story. Bad: "Task X completed: did Y, then Z."
   Good: "POST /api/agents/{id}/skills/sync — desiredSkills defaults to null,
   must be passed explicitly."
2. Dedup is automatic. Server supersedes similar memories (>0.85 similarity).
   Just write — don't pre-search.
3. Use the right type. `feedback` and `pattern` are searchable by type;
   don't dump everything as `fact`.
4. Supersede outdated memories. Bug fixed? Config changed? Call `conport_forget`.
5. Pin critical decisions. `pinned=true` for memories that must never decay.

### Choosing type + category

| What happened | memory_type | category |
|---------------|-------------|----------|
| Environment quirk | `fact` | `resource` |
| User correction | `feedback` | `area` |
| Reusable approach | `pattern` | `resource` |
| Session log / daily event | `note` | `project` |
| User preference | `tacit` | `area` |
| Architecture choice | `decision` | `area` |

### Memory types

- `fact` — durable knowledge about the environment.
- `feedback` — user/orchestrator corrected your behavior.
- `pattern` — reusable approach or recurring issue.
- `note` — daily timeline entry, event, session log.
- `tacit` — user behavior patterns and preferences.
- `decision` — architectural/design choice with rationale.

### PARA categories

- `project` — active work with a goal or deadline.
- `area` — ongoing responsibility, no end date.
- `resource` — reference material (default).
- `archive` — inactive; moved here when no longer relevant.

### Workflow

| Trigger | Action |
|---------|--------|
| Learned something reusable | `conport_remember` (fact/pattern/feedback + category) |
| End of session | `conport_remember` (type=note, category=project) |
| User corrected behavior | `conport_remember` (type=feedback, category=area) |
| Need past context | recall is auto-injected; call `conport_recall` for targeted lookups |
| Memory outdated | `conport_forget` (soft) or with `hard_delete=true` |
| Architectural decision | `conport_remember` (type=decision, pinned=true, category=area) |
| Link related memories | `conport_link_memories` (relation_type: supersedes, derives_from, contradicts, supports, related_to) |
| End of day / week | `conport_reflect` (scope=day or week) |

### Checklist
- New learning saved with correct type + category?
- No secrets in memory content?
- Outdated memories superseded or forgotten?
- `conport_reflect(scope="day")` at end of session for consolidation?
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
        identity = {
            "agent_uuid": agent.get("uuid") or agent.get("agent_uuid"),
            "agent_name": agent.get("name", agent_name),
        }
        _save(hermes_home, identity)
        print(f"  Bound to ConPort agent: {identity['agent_name']} ({identity['agent_uuid']})")

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        """Hermes runtime context arrives via kwargs (run_agent.py:1705).

        We capture: hermes_home (storage scope), agent_context (writes-allowed
        gate), agent_identity (profile name), platform (origin tag).
        Other kwargs (user_id, chat_id, ...) are accepted but unused in v0.1.
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

    def _load_provider_config(self) -> dict[str, Any]:
        if not self._hermes_home:
            return {}
        p = Path(self._hermes_home) / PROVIDER_CONFIG_FILENAME
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def _load_agent_uuid(self) -> str | None:
        if not self._hermes_home:
            return None
        p = Path(self._hermes_home) / IDENTITY_FILENAME
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text()).get("agent_uuid")
        except (OSError, json.JSONDecodeError):
            return None

    # --- tool surface (per MemoryProvider contract) ---

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        if not (self._client and self._agent_uuid):
            return []
        return list(TOOL_SCHEMAS)

    def handle_tool_call(self, name: str, args: dict[str, Any]) -> str:
        if not (self._client and self._agent_uuid):
            return json.dumps({"error": "ConPort provider not initialized; run `hermes conport-hermes init`."})
        return dispatch_tool(
            tool_name=name, args=args, client=self._client, agent_uuid=self._agent_uuid
        )

    # --- optional hooks ---

    def system_prompt_block(self) -> str | None:
        if not self._agent_uuid:
            return None
        return _SYSTEM_PROMPT_BLOCK

    def prefetch(self, query: str) -> str | None:
        if not (self._client and self._agent_uuid):
            return None
        try:
            memories = self._client.recall(
                agent_uuid=self._agent_uuid,
                query=query,
                limit=self._recall_limit,
                timeout=self._recall_timeout,
            )
        except Exception:  # noqa: BLE001 — non-blocking is required
            return None
        if not memories:
            return None
        lines = [
            f"- ({m.get('memory_type', 'note')}) {m.get('content', '')}" for m in memories
        ]
        return "Relevant ConPort memories:\n" + "\n".join(lines)

    def sync_turn(self, user_content: str, assistant_content: str) -> None:
        # No implicit writes — agent uses explicit conport_remember tool.
        # If implicit extraction is added later, gate it on
        # self._agent_context == "primary" (cron/subagent must not write).
        return None

    def on_session_end(self, messages: list[dict[str, Any]]) -> None:
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
