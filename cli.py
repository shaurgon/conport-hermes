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

# Hermes' discover_plugin_cli_commands loads cli.py standalone (no parent
# package set up), so relative imports fail at argparse-build time. We
# fall back to importlib loading the sibling files into private locals —
# crucially WITHOUT modifying sys.path, since polluting sys.path with the
# plugin directory makes Hermes' `import tools.*` resolve to our tools.py.
try:
    from .client import ConPortClient
    from .setup_wizard import run_identity_wizard
except ImportError:
    import importlib.util
    from pathlib import Path

    def _load_sibling(name: str):
        path = Path(__file__).resolve().parent / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"_conport_hermes_cli_{name}", str(path))
        if not spec or not spec.loader:
            raise ImportError(name)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    _client_mod = _load_sibling("client")
    _setup_mod = _load_sibling("setup_wizard")
    ConPortClient = _client_mod.ConPortClient  # type: ignore[no-redef]
    run_identity_wizard = _setup_mod.run_identity_wizard  # type: ignore[no-redef]

DEFAULT_API_BASE = "https://api.conport.app"


def _hermes_home() -> str:
    return os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))


def _api_base() -> str:
    p = os.path.join(_hermes_home(), "conport_provider.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f).get("api_base_url", DEFAULT_API_BASE)
        except (OSError, json.JSONDecodeError):
            pass
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
        identity = json.load(f)
    return ConPortClient(base_url=_api_base(), api_key=api_key), identity["agent_uuid"]


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
            recent = client.list_memories(uuid, limit=1)
            print(f"agent_uuid     {uuid}")
            print(f"agent_name     {agent.get('name', '')}")
            print(f"memory_count   {agent.get('memory_count', '?')}")
            if recent:
                print(f"last_activity  {recent[0].get('created_at', '?')}")
        elif sub == "agent":
            print(json.dumps(client.get_agent(uuid), indent=2))
        elif sub == "reflect":
            print(json.dumps(client.reflect(uuid, scope=args.scope), indent=2))
        elif sub == "memories":
            for m in client.list_memories(uuid, limit=args.limit):
                snippet = (m.get("content") or "")[:120]
                print(f"#{m.get('id', '?')} ({m.get('memory_type', 'note')}) {snippet}")
        elif sub == "tail":
            seen: set = set()
            try:
                while True:
                    for m in client.list_memories(uuid, limit=args.limit):
                        mid = m.get("id")
                        if mid is None or mid in seen:
                            continue
                        seen.add(mid)
                        snippet = (m.get("content") or "")[:200]
                        print(f"#{mid} ({m.get('memory_type')}) {snippet}")
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                pass
        else:
            raise SystemExit(
                "Usage: hermes conport-hermes "
                "{init|status|agent|reflect|memories|tail}"
            )
    finally:
        client.close()


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Build the ``hermes conport-hermes`` argparse tree.

    Hermes discovers this function and calls it with the parser created
    via ``subparsers.add_parser("conport-hermes", ...)``.
    """

    sub = subparser.add_subparsers(dest="conport_hermes_subcommand", required=True)

    sub.add_parser("init", help="Run identity wizard (create or attach an agent)")
    sub.add_parser("status", help="Identity, memory count, last activity")
    sub.add_parser("agent", help="Show full agent record")

    refl = sub.add_parser("reflect", help="Manually trigger reflect")
    refl.add_argument("--scope", default="day", choices=["day", "week", "full"])

    mem = sub.add_parser("memories", help="List recent memories")
    mem.add_argument("--limit", type=int, default=20)

    tail = sub.add_parser("tail", help="Stream new memories (poll)")
    tail.add_argument("--limit", type=int, default=10)
    tail.add_argument("--interval", type=float, default=2.0)

    subparser.set_defaults(func=conport_hermes_command)
