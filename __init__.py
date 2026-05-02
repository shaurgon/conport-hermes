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
from .cli import register_cli
from .tools import TOOL_SCHEMAS, dispatch_tool

__version__ = "0.1.1"

PROVIDER_NAME = "conport"
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
        return [
            {
                "key": "api_key",
                "secret": True,
                "env_var": "CONPORT_API_KEY",
                "required": True,
                "description": "ConPort API key (cport_live_...). Create one in your ConPort dashboard.",
            },
            {
                "key": "api_base_url",
                "secret": False,
                "default": DEFAULT_API_BASE,
                "description": "ConPort API base URL.",
            },
            {
                "key": "recall_limit",
                "secret": False,
                "default": 5,
                "description": "Max memories returned per prefetch.",
            },
            {
                "key": "recall_timeout_seconds",
                "secret": False,
                "default": 2,
                "description": "Hard timeout for prefetch (must stay non-blocking).",
            },
        ]

    def save_config(self, values: dict[str, Any], hermes_home: str) -> None:
        non_secret = {k: v for k, v in values.items() if k != "api_key"}
        path = Path(hermes_home) / PROVIDER_CONFIG_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(non_secret, indent=2))

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
            return json.dumps({"error": "ConPort provider not initialized; run `hermes conport init`."})
        return dispatch_tool(
            tool_name=name, args=args, client=self._client, agent_uuid=self._agent_uuid
        )

    # --- optional hooks ---

    def system_prompt_block(self) -> str | None:
        if not self._agent_uuid:
            return None
        return (
            "You have access to ConPort long-term memory. "
            "Use `conport_remember` to persist durable facts, decisions, and lessons. "
            "Use `conport_recall` to surface relevant prior context."
        )

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
    """Hermes calls this on plugin load."""
    ctx.register_memory_provider(ConPortMemoryProvider())
    register_cli(ctx)


__all__ = ["ConPortMemoryProvider", "register", "__version__"]
