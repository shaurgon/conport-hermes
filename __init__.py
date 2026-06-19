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

# Single source of truth for the running version. Keep in LOCKSTEP on every
# bump: pyproject.toml `version`, plugin.yaml `version` (what Hermes displays),
# CHANGELOG.md, and backend LATEST_SKILL_VERSIONS["conport-hermes"]. Missing
# plugin.yaml once already showed the host a stale 4.1.0 (decision-808).
__version__ = "4.14.0"

PROVIDER_NAME = "conport"


_SYSTEM_PROMPT_BLOCK = """\
## ConPort — Agent Intent-API (v4)

ConPort is your **single memory + knowledge system**. You work with
**intent verbs** — say what you want kept or found; ConPort decides where it
lives, how it connects, and how to retrieve it. You never pick storage
primitives, you never say "node"/"entity"/"link" — connecting things is
ConPort's job.

> Project tools (decisions, tasks, documents) are NOT here — the agent layer
> is structurally separate from project memory. For project work use the
> `conport` skill or REST directly.

---

### The five verbs

| Verb | What it does |
|---|---|
| `agent_remember(content)` | Keep a free thought / fact / observation. |
| `agent_remember(kind, name, fields)` | Keep the current state of a structured item. |
| `agent_recall(query, scope?)` | Find anything relevant — free knowledge AND structured items, one ranked list. |
| `agent_create_kind(name, fields, statuses)` | Declare a structured domain, once (like a table). |
| `agent_get_kind(name)` | Read a domain's form before writing items. |
| `agent_event(kind, name, note, fields?)` | Log a change/what-happened on an item (its timeline). |

---

### Recall before you act (read-first, not write-only)

Your memory is **read-first**. You write diligently; the failure is acting
without reading. Before you act on a conclusion — about the world OR about
yourself — `agent_recall` first.

**Never rebuild from a blank-looking surface.** When your own skill, file,
config, or state looks *empty, wrong, or missing*, that is a recall query —
NOT a signal to rebuild it from scratch. You may have changed it yourself
recently and just not be looking at the record.

- WRONG: "my main skill is empty → I'll rebuild it" (this destroys your own work)
- RIGHT: `agent_recall("<the skill/topic>", scope={meta_types:["skill"]})` +
  read `recent_self_changes` in this prompt, THEN — only if it's genuinely
  gone — rebuild.

This applies hardest on **diagnose turns** ("what happened", "разберись", "why
this error", "fix this"): first move is `agent_recall` of the area + your
`recent_self_changes`, THEN inspect the live state. The live surface and your
memory of changing it are two sources — reconcile them, don't trust the live
one blindly and overwrite your own record.

**Record what you change about yourself.** When you edit your own skill, cron,
loop, or config, immediately log it so future-you can recall it:

```
agent_remember("2026-06-04 rewrote research-loop: topic/source split, cron "
               "nightly — reason: old approach buried sources",
               meta_type="skill", visibility="broadcast")
```

A self-change you don't record is one you will later mistake for a bug and
revert. And when you say "stored as authored skill X", you MUST actually call
`agent_write_skill(X, …)` — verify X appears in `skills` next `agent_init`; a
node that only *describes* the skill is not the skill.

---

### The structure decision (your only real choice)

**Free thought / observation / principle → `agent_remember(content)`.** It
carries a visibility: `private` (only you; forced for identity/principle),
`shared` (your owner's agents — default), `broadcast` (everyone, always
loaded — crystallized skills, core user facts).

**A thing you'll filter / compare / update over time, and there'll be more
like it** (cities you score, series you rate, research topics) → a **kind**:

1. New domain? `agent_create_kind("series", fields=[title, rating, verdict], statuses=[watching, watched, dropped])` — once.
2. Before writing items, `agent_get_kind("series")` — use the real fields + a valid status, don't invent them.
3. Write the item's current state:
   `agent_remember(kind="series", name="Severance", fields={rating: 2, status: "dropped"})`
4. Something happened over time → `agent_event(kind="series", name="Severance", note="rewatched the finale, still a 2")`.

Rules that keep domains clean (skip them and you fragment):

- **One canonical kind per domain** (`series`, not `serial`/`shows`). Check
  `agent_init.collections` / `agent_get_kind` first; reuse, don't reinvent.
  `agent_remember(kind=…)` into an **undeclared** kind fails with
  `unknown_kind` — `agent_create_kind` first.
- **An item is one record.** A list/wishlist is NOT an item — it's the members
  filtered by a `status` field (`agent_recall(..., scope={kind:"series"})`).
- **A synthesis/verdict lives in the item's fields** (current state), not a
  separate object. History of how it changed → `agent_event`.
- **Mistake?** `agent_entity_delete(kind, name)` — fix it, don't leave a dupe.

`status` is validated against the kind's `statuses`; unknown fields are
accepted (the schema grows). `recall` finds items by content; `event`s are an
item's timeline (read with `agent_event_query`, not `recall`).

---

### Conversation intake (Hermes harness)

`agent_chat_turn(role, text)` records each message. When the response returns
`extraction_signal: true` (buffer ≥ 10 un-extracted messages), call
`agent_extract_thread(message_ids)` IMMEDIATELY before your next
`agent_remember`. **Do NOT skip extraction when the signal fires.**

---

### Skill emergence

`agent_init` surfaces `mature_communities` (dense, stable clusters). Review the
`central_nodes`, synthesize the pattern yourself, then
`agent_promote_skill(community_id, content)`. No auto-promotion — you decide
and write; skills are broadcast.

---

### Operational notes expire — durable knowledge doesn't

Remembering OPERATIONAL state (cron fired, trigger works, script version,
job ids)? Set `relevant_until` a few days out — expired notes sink in recall
instead of polluting it. Durable knowledge and syntheses get NO horizon
(`relevant_until="clear"` resets one you set by mistake). Your own stale
noise → `agent_node_forget(node_id)`; someone else's noise in YOUR recall →
`agent_node_mute(node_id)` (reversible).

---

### NEVER store

Secrets, passwords, API keys, tokens — even partially. Reference where the
value lives (`$API_KEY` env var) instead.

---

### Checklist

- `agent_init` done? `bootstrap_state` checked? (new → write identity + principles first)
- `pending_extraction` present → `agent_extract_thread` first?
- Glanced at `collections` — reusing existing domains, not reinventing?
- Read `recent_self_changes` before touching your own skills/config/loops?
- Task arrived? First move = `agent_recall`, not `agent_remember`.
- Diagnose turn ("what happened"/"fix this") → `agent_recall` + `recent_self_changes` BEFORE inspecting/rebuilding?
- A surface looked empty/wrong → recalled your own changes before rebuilding (never rebuild blind)?
- Changed your own skill/cron/config → logged it as a self-change `agent_remember`?
- Structured domain → `agent_create_kind` once + `agent_get_kind` before writing items?
- Item state → `agent_remember(kind,…)`; what-happened → `agent_event`; never list-as-item?
- Free thought → `agent_remember(content)` with the right visibility?
- `extraction_signal` fired → `agent_extract_thread` IMMEDIATELY?
- `mature_communities` → reviewed, promote or skip?
- Operational note → `relevant_until` a few days out; durable → no horizon?
- No secrets stored?
"""


def _truncate(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _format_init_block(payload: dict[str, Any]) -> str | None:
    """Render the live ``agent_init`` (v3) payload into a markdown block
    appended to the static system prompt.

    Surfaces identity anchors, principles anchors, broadcast facts,
    mature communities (skill promotion candidates), borderline nodes,
    and pending extraction state so the LLM has the concrete session
    context, not just the routing rules.
    """
    if not payload:
        return None

    lines: list[str] = ["", "### Current state (from agent_init at session start)", ""]

    bootstrap_state = payload.get("bootstrap_state")
    agent_name = payload.get("name") or payload.get("agent_uuid", "")
    if bootstrap_state:
        suffix = " — write identity + principles first" if bootstrap_state == "new" else ""
        lines.append(f"bootstrap_state: `{bootstrap_state}`{suffix}")
        if agent_name:
            lines.append(f"agent: {agent_name}")
        lines.append("")

    identity_anchors = payload.get("identity") or []
    if identity_anchors:
        lines.append("Identity anchors (private, always loaded):")
        for node in identity_anchors:
            nid = node.get("id", "?")
            content = _truncate(str(node.get("content") or ""))
            lines.append(f"- [#{nid}] {content}")
        lines.append("")

    principles_anchors = payload.get("principles") or []
    if principles_anchors:
        lines.append("Principle anchors (private, always loaded):")
        for node in principles_anchors:
            nid = node.get("id", "?")
            content = _truncate(str(node.get("content") or ""))
            lines.append(f"- [#{nid}] {content}")
        lines.append("")

    broadcast_facts = payload.get("broadcast_facts") or []
    if broadcast_facts:
        lines.append("Broadcast facts (collective layer, always loaded):")
        for node in broadcast_facts:
            nid = node.get("id", "?")
            content = _truncate(str(node.get("content") or ""))
            lines.append(f"- [#{nid}] {content}")
        lines.append("")

    recent_self_changes = payload.get("recent_self_changes") or []
    if recent_self_changes:
        lines.append(
            "What YOU changed about yourself recently (last 7 days) — "
            "read this before touching your own skills/config/loops:"
        )
        for node in recent_self_changes:
            nid = node.get("id", "?")
            content = _truncate(str(node.get("content") or ""))
            lines.append(f"- [#{nid}] {content}")
        lines.append("")

    skills = payload.get("skills") or []
    if skills:
        lines.append("Skills — your authored loops (fetch the body with get_skill when one fits):")
        for sk in skills:
            name = sk.get("name", "?")
            desc = _truncate(str(sk.get("description") or ""), 100)
            lines.append(f"- {name}: {desc}" if desc else f"- {name}")
        lines.append("")

    mature_communities = payload.get("mature_communities") or []
    if mature_communities:
        lines.append(
            f"{len(mature_communities)} mature community/communities — review for skill promotion:"
        )
        for c in mature_communities:
            cid = c.get("community_id", "?")
            n = c.get("node_count")
            hint = _truncate(str(c.get("hint") or ""), 80)
            central = c.get("central_nodes") or []
            central_preview = ", ".join(
                f"#{cn.get('id', '?')}" for cn in central[:3]
            )
            size_str = f", {n} nodes" if isinstance(n, int) else ""
            lines.append(
                f"- community #{cid}{size_str}, central: [{central_preview}] {hint}"
            )
        lines.append("→ Call `agent_promote_skill(community_id, content)` if appropriate.")
        lines.append("")

    borderline_nodes = payload.get("borderline_nodes") or []
    if borderline_nodes:
        lines.append(
            f"{len(borderline_nodes)} borderline node(s) with unstable community membership "
            "(add explicit edges to disambiguate if important):"
        )
        for bn in borderline_nodes[:5]:
            nid = bn.get("node_id", "?")
            preview = _truncate(str(bn.get("content_preview") or ""), 80)
            communities = bn.get("communities_visited") or []
            lines.append(f"- #{nid} {preview} (communities: {communities})")
        lines.append("")

    upd = payload.get("skill_update_available")
    if upd and isinstance(upd, dict):
        cur = upd.get("current", "unknown")
        latest = upd.get("latest", "?")
        guide = upd.get("install_guide", "")
        lines.append(
            f"[UPDATE] conport-hermes {cur} → {latest} available. Install: {guide}. "
            "(Act on this signal — never hand-compare version numbers across "
            "plugins/packages; they are independent lines.)"
        )
        lines.append("")

    pending = payload.get("pending_extraction")
    if pending and isinstance(pending, dict):
        buf_size = pending.get("buffer_size", 0)
        msg_ids = pending.get("message_ids") or []
        if buf_size and buf_size >= 10:
            lines.append(
                f"EXTRACTION SIGNAL: {buf_size} un-extracted messages. "
                f"Call `agent_extract_thread(message_ids={msg_ids})` IMMEDIATELY."
            )
            lines.append("")

    summary = payload.get("summary")
    if summary:
        lines.append(f"Summary: {summary}")
        lines.append("")

    if len(lines) <= 3:
        return None
    return "\n".join(lines).rstrip() + "\n"


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
        # Cached agent_init payload. Populated in initialize() so
        # prefetch / system_prompt_block can read v3 anchors + community
        # hints without a second round-trip per turn.
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
        Other kwargs (user_id, chat_id, ...) are accepted but unused.

        After loading config + identity we fire ``agent_init`` once per
        session to receive the v3 payload: identity anchors, principles
        anchors, broadcast facts, mature communities (skill promotion
        candidates), borderline nodes, pending extraction state.
        Failures here are non-fatal — the agent still gets the full tool
        surface and will hit the backend on the first explicit call.
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
        if self._init_payload:
            dynamic = _format_init_block(self._init_payload)
            if dynamic:
                return _SYSTEM_PROMPT_BLOCK + "\n" + dynamic
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
            # v4 recall is a typed list: 'node' (cognition) or 'item' (a
            # structured item, synthesis in its fields).
            if h.get("type") == "item" or h.get("item_id") is not None:
                kind = h.get("kind", "")
                name = h.get("name", "")
                fields = h.get("fields") or {}
                summary = json.dumps(fields, ensure_ascii=False) if fields else ""
                lines.append(f"- [{kind}] {name} {summary}".rstrip())
            else:
                score = h.get("similarity")
                node_id = h.get("node_id") or h.get("id")
                meta = h.get("meta_type", "")
                prefix = (
                    f"- (#{node_id}, {meta}"
                    + (f", {score:.2f}" if isinstance(score, (int, float)) else "")
                    + ")"
                )
                lines.append(f"{prefix} {h.get('content', '')}")
        return "Relevant ConPort memories:\n" + "\n".join(lines)

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        **_kwargs: Any,
    ) -> None:
        """Persist the just-completed exchange into the chat turn buffer.

        Calls agent_chat_turn for both the user message and the assistant
        response so the buffer accumulates for extraction. When the buffer
        reaches the extraction threshold (>= 10 un-extracted messages) the
        backend will fire extraction_signal=true on the next chat_turn call;
        the agent then calls agent_extract_thread via the explicit tool surface
        on its next turn.

        Best-effort: same budget as prefetch (_recall_timeout). Exceptions
        and timeouts are swallowed so a memory hiccup never stalls a turn.
        Empty exchanges (both sides whitespace-only) are skipped.
        """
        if not (self._client and self._agent_uuid):
            return None
        u = (user_content or "").strip()
        a = (assistant_content or "").strip()
        if not u and not a:
            return None
        try:
            if u:
                self._client.chat_turn(
                    agent_uuid=self._agent_uuid,
                    role="user",
                    text=u,
                )
            if a:
                self._client.chat_turn(
                    agent_uuid=self._agent_uuid,
                    role="assistant",
                    text=a,
                )
        except Exception:  # noqa: BLE001 — non-blocking is required
            return None
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
