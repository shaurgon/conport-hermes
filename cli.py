"""``hermes conport-hermes <subcommand>`` — discovered by
plugins.memory.discover_plugin_cli_commands when this plugin is the
active memory provider.

Convention (mirrors plugins/memory/honcho/cli.py):
- ``register_cli(subparser)`` populates the argparse tree and calls
  ``subparser.set_defaults(func=conport_hermes_command)``.
- ``conport_hermes_command(args)`` dispatches by the
  ``conport_hermes_subcommand`` value populated by argparse.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from types import ModuleType
from typing import TYPE_CHECKING, cast

from .models import IdentityFile, ProviderConfig

if TYPE_CHECKING:
    from .client import ConPortClient
    from .setup_wizard import run_identity_wizard
else:
    # Hermes' discover_plugin_cli_commands loads cli.py standalone (no parent
    # package set up), so relative imports fail at argparse-build time. Fall
    # back to importlib loading the sibling files into private locals —
    # crucially WITHOUT modifying sys.path, since polluting sys.path with the
    # plugin directory makes Hermes' `import tools.*` resolve to our tools.py.
    try:
        from .client import ConPortClient
        from .setup_wizard import run_identity_wizard
    except ImportError:
        import importlib.util
        from pathlib import Path

        def _load_sibling(name: str) -> ModuleType:
            path = Path(__file__).resolve().parent / f"{name}.py"
            spec = importlib.util.spec_from_file_location(
                f"_conport_hermes_cli_{name}", str(path)
            )
            if not spec or not spec.loader:
                raise ImportError(name)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        _client_mod = _load_sibling("client")
        _setup_mod = _load_sibling("setup_wizard")
        ConPortClient = _client_mod.ConPortClient
        run_identity_wizard = _setup_mod.run_identity_wizard

DEFAULT_API_BASE = "https://api.conport.app"


def _hermes_home() -> str:
    return os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))


def _api_base() -> str:
    p = os.path.join(_hermes_home(), "conport_provider.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            raw = None
        if isinstance(raw, dict):
            cfg = cast(ProviderConfig, raw)
            value = cfg.get("api_base_url")
            if isinstance(value, str) and value:
                return value
    return os.environ.get("CONPORT_API_BASE_URL", DEFAULT_API_BASE)


def _api_key() -> str | None:
    """Resolve API key — env first, then $HERMES_HOME/.env (for cron contexts)."""
    key = os.environ.get("CONPORT_API_KEY")
    if key:
        return key
    env_file = os.path.join(_hermes_home(), ".env")
    if not os.path.exists(env_file):
        return None
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("CONPORT_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    except OSError:
        return None
    return None


def _client_and_uuid() -> tuple[ConPortClient, str]:
    api_key = _api_key()
    if not api_key:
        raise SystemExit(
            "CONPORT_API_KEY is not set. Run `hermes memory setup` first."
        )
    identity_file = os.path.join(_hermes_home(), "conport.json")
    if not os.path.exists(identity_file):
        raise SystemExit(
            f"No identity at {identity_file}. Run `hermes conport-hermes init`."
        )
    with open(identity_file) as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise SystemExit(f"Identity file {identity_file} is not a JSON object.")
    identity = cast(IdentityFile, raw)
    agent_uuid = identity.get("agent_uuid")
    if not isinstance(agent_uuid, str) or not agent_uuid:
        raise SystemExit(f"Identity file {identity_file} missing agent_uuid.")
    return ConPortClient(base_url=_api_base(), api_key=api_key), agent_uuid


def conport_hermes_command(args: argparse.Namespace) -> None:
    """Top-level dispatcher for ``hermes conport-hermes <subcommand>``."""

    sub = getattr(args, "conport_hermes_subcommand", None)

    if sub == "init":
        api_key = _api_key()
        if not api_key:
            raise SystemExit("CONPORT_API_KEY is not set. Run `hermes memory setup` first.")
        run_identity_wizard(
            hermes_home=_hermes_home(),
            api_base_url=_api_base(),
            api_key=api_key,
        )
        return

    client, uuid = _client_and_uuid()
    try:
        if sub == "status":
            agent = client.get_agent(uuid)
            payload = client.agent_init(uuid)
            print(f"agent_uuid       {uuid}")
            print(f"agent_name       {agent.get('name', '')}")
            print(f"bootstrap_state  {payload.get('bootstrap_state', '?')}")
            print(f"trunk_root_id    {payload.get('trunk_root_id', '?')}")
            print(f"active_branches  {len(payload.get('active_branches', []) or [])}")
            print(f"lift_candidates  {payload.get('pending_lift_candidates', 0)}")
            print(f"conflicts        {payload.get('pending_promotion_conflicts', 0)}")
        elif sub == "agent":
            print(json.dumps(client.get_agent(uuid), indent=2, ensure_ascii=False))
        elif sub == "reflect":
            print(
                json.dumps(
                    client.reflect(uuid, node_id=args.node_id, new_content=args.new_content),
                    indent=2,
                    ensure_ascii=False,
                )
            )
        elif sub == "branches":
            print(
                json.dumps(
                    client.list_branches(uuid, state=args.state),
                    indent=2,
                    ensure_ascii=False,
                )
            )
        elif sub == "tail":
            # Poll the active-branches list. Cron-style watch — useful from an
            # operator shell, not from inside the agent loop.
            seen: set[int] = set()
            try:
                while True:
                    for b in client.list_branches(uuid, state="active"):
                        bid = b.get("branch_id")
                        if not isinstance(bid, int) or bid in seen:
                            continue
                        seen.add(bid)
                        preview = (b.get("origin_content_preview") or "")[:200]
                        print(f"branch-{bid} ({b.get('branch_state', '?')}) {preview}")
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                pass
        else:
            raise SystemExit(
                "Usage: hermes conport-hermes "
                "{init|status|agent|reflect|branches|tail}"
            )
    finally:
        client.close()
    return None


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes conport-hermes`` argparse tree.

    Hermes discovers this function and calls it with the parser created
    via ``subparsers.add_parser("conport-hermes", ...)``.
    """

    sub = subparser.add_subparsers(dest="conport_hermes_subcommand", required=True)

    sub.add_parser("init", help="Run identity wizard (create or attach an agent)")
    sub.add_parser("status", help="Identity + bootstrap state + counters")
    sub.add_parser("agent", help="Show full agent record")

    refl = sub.add_parser("reflect", help="Manually invoke gravity on a node")
    refl.add_argument("--node-id", dest="node_id", type=int, required=True)
    refl.add_argument(
        "--new-content",
        dest="new_content",
        default=None,
        help="Merged content; omit for bookkeeping-only reflect.",
    )

    br = sub.add_parser("branches", help="List branches optionally by state")
    br.add_argument("--state", choices=["active", "dormant", "closed"], default=None)

    tail = sub.add_parser("tail", help="Stream new active branches (poll)")
    tail.add_argument("--interval", type=float, default=2.0)

    subparser.set_defaults(func=conport_hermes_command)
