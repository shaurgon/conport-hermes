# conport-hermes

ConPort memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — long-term knowledge graph for autonomous agents, with semantic recall, decay-aware scoring, and reflection.

```bash
hermes plugins install shaurgon/conport-hermes
hermes memory setup     # pick `conport-hermes`, paste cport_live_… key — done
```

A default ConPort agent is auto-created and bound to your Hermes profile in one shot. `hermes conport-hermes init` is only needed to rebind to a different agent.

## What you get

- **Cross-session memory** backed by ConPort's knowledge graph
- **Auto-recall** injected before every turn (non-blocking, 2-second budget)
- **Agent-memory tools (5):** `conport_remember`, `conport_recall`, `conport_forget`, `conport_reflect`, `conport_link_memories`
- **Reflection** — dedup, supersede stale memories, surface patterns
- **CLI** — `hermes conport-hermes status | agent | memories | reflect | tail | init`

> **v0.6.0 — project tools removed (decision-660).** Earlier versions
> shipped `conport_attach_project` + 14 project-level tools (search,
> tasks, decisions, progress, documents, blocks). Harness agents work
> in continuous conversation streams with dozens of context switches
> per day — session-state with one "attached project" + per-project
> scope is incompatible with that runtime. Project work
> (decisions / tasks / docs) lives in the dedicated `conport` skill
> or direct ConPort MCP/REST calls now, not through this provider.
> Migration: nothing to do for code that only used the agent-memory
> tools; code using project tools needs to switch to direct ConPort
> calls.

## Prerequisites

1. A ConPort account at <https://conport.app>
2. An API key from your ConPort dashboard (`cport_live_…`)
3. Hermes Agent installed (`pip install hermes-agent`)

## Setup walkthrough

### 1. Install

```bash
pip install conport-hermes
```

The package registers itself under the `hermes_agent.plugins` entry-point group; Hermes picks it up automatically.

### 2. Activate the provider

```bash
hermes memory setup
```

Pick `conport-hermes` from the list. The wizard prompts for one thing:

- `CONPORT_API_KEY` — your `cport_live_…` key (saved to `$HERMES_HOME/.env`)

Everything else (base URL, recall limit, prefetch timeout) ships with sane defaults. Self-hosters or tuners can override them by writing `$HERMES_HOME/conport_provider.json` directly (see [Configuration reference](#configuration-reference)).

### 3. (Optional) Rebind to a different ConPort agent

After `hermes memory setup`, your profile is auto-bound to an agent named `hermes-<hostname>`. To rebind — to attach an existing agent UUID, or pick a different name:

```bash
hermes conport-hermes init
```

Identity is persisted to `$HERMES_HOME/conport.json` and locks the profile to one ConPort agent (per decision D484).

### 4. Use it

Inside any Hermes session, the agent can now:

```
> Remember that we standardized on UTF-8 BOM-less for all source files.
[agent calls conport_remember]

> Have we made any decisions about character encoding?
[prefetch surfaces it; agent answers from recall]
```

## Configuration reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `api_key` | secret (env: `CONPORT_API_KEY`) | — | Your `cport_live_…` API key. Required. |
| `api_base_url` | string | `https://api.conport.app` | ConPort REST endpoint |
| `recall_limit` | integer | `5` | Max memories per prefetch |
| `recall_timeout_seconds` | number | `2` | Hard prefetch timeout (must stay non-blocking) |

Non-secret config is stored at `$HERMES_HOME/conport_provider.json`. The API key lives in `$HERMES_HOME/.env`.

## Tool reference

### Agent memory

| Tool | Purpose | Prompts that trigger it |
|------|---------|-------------------------|
| `conport_remember` | Persist a durable fact, decision, lesson, or pattern | "Remember that…", "Save this decision…", "Note for future me…" |
| `conport_recall` | Search prior memories (semantic + decay-aware scoring) | "What did we decide about…?", "Have we discussed X before?" |
| `conport_forget` | Soft-delete (or hard-delete) a memory by id | "Forget memory #42", "That note was wrong, remove it" |
| `conport_reflect` | Trigger consolidation: dedup, supersede stale, surface patterns | "Reflect on the last week", "Consolidate today's memories" |
| `conport_link_memories` | Connect two memories with a typed relation | Used implicitly by reflect; agents can also call directly |

### Project tools — removed in v0.6.0

Earlier versions exposed a project-shaped surface (`conport_attach_project`,
`conport_search`, `conport_add_task`, `conport_sync_decision`,
`conport_log_progress`, document tools, block tools — 14 tools total).
Removed in v0.6.0 per decision-660: harness agents work in continuous
conversation streams with dozens of context switches per day, not
project-shaped tasks. The "currently attached project" pattern is
incompatible with that runtime.

If you need project work from Hermes, call ConPort directly:

- Via MCP — point the harness at `https://api.conport.app/mcp` with
  your `cport_live_…` key.
- Via REST — `httpx` against `https://api.conport.app/api/v1/...` with
  `X-API-Key: cport_live_…`.

The `conport` Claude Code skill exposes the full project tool surface
if you're driving project work from Claude Code rather than Hermes.

### Memory shape

Every memory has:

- **`memory_type`** — `fact | feedback | pattern | note | tacit | decision`
- **`category`** — PARA model: `project | area | resource | archive`
- **`tags`** — free-form list, used for filtering
- **`pinned`** — when true, never decays
- **`entity_ref`** — optional canonical entity name to attach to the knowledge graph

### Link relations

`related_to | supersedes | derives_from | contradicts | supports`

## CLI reference

```bash
hermes conport-hermes status                  # identity, memory count, last activity
hermes conport-hermes agent                   # full agent record (JSON)
hermes conport-hermes memories [--limit N]    # list recent memories
hermes conport-hermes tail [--interval 2]     # poll-based stream of new memories
hermes conport-hermes reflect [--scope day]   # manual reflect; scope: day | week | full
hermes conport-hermes init                    # (re)run the identity wizard
```

## Identity model

One Hermes profile maps 1:1 to one ConPort agent (decision D484). To run multiple agents, run multiple Hermes profiles via `HERMES_HOME=~/.hermes-agent-2 hermes …`.

To **switch** profiles to a different agent, delete `$HERMES_HOME/conport.json` and re-run `hermes conport-hermes init`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `401 Unauthorized` on first call | Bad or rotated API key | Open `$HERMES_HOME/.env`, replace `CONPORT_API_KEY`; or rotate via the ConPort dashboard |
| `No identity at …/conport.json` | Wizard never ran | `hermes conport-hermes init` |
| `404` on `/agents/<uuid>` | Agent was deleted server-side | `rm $HERMES_HOME/conport.json && hermes conport-hermes init` |
| Recall returns nothing in fresh session | Brand-new agent — memory is empty | Use `conport_remember` a few times; reflect pulls patterns later |
| Recall is slow / times out | Network to ConPort exceeds 2s | Bump `recall_timeout_seconds` (but stays non-blocking by design) |
| Tool calls never reach ConPort | Provider deactivated | `hermes memory status` — confirm `conport` is the active provider |

## FAQ

**Q. How is this different from Hermes' built-in `MEMORY.md`?**
ConPort is structured, queryable, and cross-session — every memory has a type, category, tags, decay score, and graph links. `MEMORY.md` is a flat append-only file. They can coexist (different tools), but only one `MemoryProvider` is active at a time.

**Q. What happens when reflect runs?**
The server scans the agent's memories within `scope` (day, week, full), proposes dedup candidates, supersedes stale notes, surfaces emergent patterns, and groups entities. Returned as `AgentReflectResponse`; the agent can review or auto-apply.

**Q. Can I use ConPort with another MemoryProvider at the same time?**
No — Hermes activates exactly one `MemoryProvider`. You can switch via `hermes memory setup`. (The plain `MEMORY.md` file is a separate mechanism and is unaffected.)

**Q. Where is my API key stored?**
In `$HERMES_HOME/.env` (profile-scoped, never sent anywhere except `api.conport.app`). `conport_provider.json` only holds non-secret config. Rotate any time from the ConPort dashboard.

**Q. Will the agent see my memories from other Hermes profiles?**
No — each Hermes profile binds to one ConPort agent UUID, and ConPort's row-level security scopes memories to the agent. Different profile = different agent = different memory pool.

**Q. Does this work with ConPort self-hosted?**
Yes. Set `api_base_url` to your instance URL during `hermes memory setup`.

## Daily reflect (optional)

Hermes' `cron` is LLM-driven and would launch a full session per run; for our
reflect (a single REST call) that's overkill. Use system cron instead — the
CLI auto-loads `CONPORT_API_KEY` from `$HERMES_HOME/.env`, so no env wiring:

```cron
# crontab -e
0 3 * * * /home/USER/.hermes/hermes-agent/venv/bin/hermes conport-hermes reflect --scope day > /tmp/conport-reflect.log 2>&1
```

Weekly: replace `--scope day` with `--scope week`.

## Status

**Alpha** (v0.1.4). E2E-validated against `hermes-agent v0.12.0` and production `api.conport.app` — all five tools, identity wizard, prefetch, error paths, and shutdown round-trip cleanly. See [VALIDATION.md](VALIDATION.md) for the full report.

## Source

This package lives in the [conport-global](https://github.com/shaurgon/conport-global) monorepo under `plugins/conport-hermes/`. File issues there.

## License

MIT
