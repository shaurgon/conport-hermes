"""`hermes conport <subcommand>` — registered via ctx.register_cli_command."""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from .client import ConPortClient
from .setup_wizard import run_identity_wizard

DEFAULT_API_BASE = "https://api.conport.app"


def _hermes_home() -> str:
    return os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))


def _api_base() -> str:
    p = os.path.join(_hermes_home(), "conport_provider.json")
    if os.path.exists(p):
        try:
            return json.load(open(p)).get("api_base_url", DEFAULT_API_BASE)
        except (OSError, json.JSONDecodeError):
            pass
    return os.environ.get("CONPORT_API_BASE_URL", DEFAULT_API_BASE)


def _client_and_uuid() -> tuple[ConPortClient, str]:
    api_key = os.environ.get("CONPORT_API_KEY")
    if not api_key:
        raise SystemExit("CONPORT_API_KEY is not set; run `hermes plugins install conport-hermes`.")
    identity_file = os.path.join(_hermes_home(), "conport.json")
    if not os.path.exists(identity_file):
        raise SystemExit(f"No identity at {identity_file}; run `hermes conport init`.")
    with open(identity_file) as f:
        identity = json.load(f)
    return ConPortClient(base_url=_api_base(), api_key=api_key), identity["agent_uuid"]


def _setup_argparse(subparser: argparse.ArgumentParser) -> None:
    sub = subparser.add_subparsers(dest="conport_cmd", required=True)

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


def _handle(args: argparse.Namespace) -> None:
    cmd = getattr(args, "conport_cmd", None)
    if cmd == "init":
        api_key = os.environ.get("CONPORT_API_KEY")
        if not api_key:
            raise SystemExit("CONPORT_API_KEY is not set; run plugin install first.")
        run_identity_wizard(
            hermes_home=_hermes_home(),
            api_base_url=_api_base(),
            api_key=api_key,
        )
        return

    client, uuid = _client_and_uuid()
    try:
        if cmd == "status":
            agent = client.get_agent(uuid)
            recent = client.list_memories(uuid, limit=1)
            print(f"agent_uuid     {uuid}")
            print(f"agent_name     {agent.get('name', '')}")
            print(f"memory_count   {agent.get('memory_count', '?')}")
            if recent:
                print(f"last_activity  {recent[0].get('created_at', '?')}")
        elif cmd == "agent":
            print(json.dumps(client.get_agent(uuid), indent=2))
        elif cmd == "reflect":
            print(json.dumps(client.reflect(uuid, scope=args.scope), indent=2))
        elif cmd == "memories":
            for m in client.list_memories(uuid, limit=args.limit):
                snippet = (m.get("content") or "")[:120]
                print(f"#{m.get('id', '?')} ({m.get('memory_type', 'note')}) {snippet}")
        elif cmd == "tail":
            seen: set[Any] = set()
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
            raise SystemExit(f"Unknown subcommand: {cmd}")
    finally:
        client.close()


def register_cli(ctx: Any) -> None:
    if not hasattr(ctx, "register_cli_command"):
        return
    ctx.register_cli_command(
        name="conport",
        help="ConPort memory provider commands",
        setup_fn=_setup_argparse,
        handler_fn=_handle,
    )
