"""Identity wizard run by `hermes conport init`.

Per decision D484: one Hermes profile maps 1:1 to one ConPort agent.
Persists {agent_uuid, agent_name} to $HERMES_HOME/conport.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


def _identity_path(hermes_home: str) -> Path:
    return Path(hermes_home) / "conport.json"


def _load_existing(hermes_home: str) -> dict[str, Any] | None:
    p = _identity_path(hermes_home)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _save(hermes_home: str, identity: dict[str, Any]) -> None:
    p = _identity_path(hermes_home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(identity, indent=2))


def _validate_agent(api_base_url: str, api_key: str, agent_uuid: str) -> dict[str, Any]:
    r = httpx.get(
        f"{api_base_url.rstrip('/')}/api/v1/agents/{agent_uuid}",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _create_agent(api_base_url: str, api_key: str, name: str) -> dict[str, Any]:
    r = httpx.post(
        f"{api_base_url.rstrip('/')}/api/v1/agents",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"name": name, "type": "worker"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def run_identity_wizard(
    *,
    hermes_home: str,
    api_base_url: str,
    api_key: str,
    prompt: Any = input,
    out: Any = print,
) -> dict[str, Any]:
    """Interactive wizard. `prompt` and `out` injectable for tests."""

    existing = _load_existing(hermes_home)
    if existing and "agent_uuid" in existing:
        out(
            f"Found existing ConPort identity: "
            f"{existing.get('agent_name')} ({existing['agent_uuid']})"
        )
        if prompt("Reuse it? [Y/n] ").strip().lower() in ("", "y", "yes"):
            return existing

    out("ConPort agent setup — one Hermes profile maps to one ConPort agent.")
    choice = prompt("[1] Create new agent  [2] Attach to existing UUID  > ").strip()

    if choice == "2":
        uuid = prompt("Existing agent UUID: ").strip()
        agent = _validate_agent(api_base_url, api_key, uuid)
    else:
        name = prompt("Name for the new agent: ").strip() or "hermes-agent"
        agent = _create_agent(api_base_url, api_key, name)

    identity = {
        "agent_uuid": agent.get("uuid") or agent.get("agent_uuid"),
        "agent_name": agent.get("name", ""),
    }
    _save(hermes_home, identity)
    out(f"Saved → {_identity_path(hermes_home)}")
    return identity
