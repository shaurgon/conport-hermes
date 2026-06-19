# conport-hermes

ConPort memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — a long-term knowledge graph for autonomous agents on ConPort's **Agent Intent-API (v4)**. The agent works with **intent verbs** (create_kind / get_kind / remember / event / recall); ConPort decides where data lives, how it connects, and how to retrieve it.

```bash
hermes plugins install shaurgon/conport-hermes
hermes memory setup     # pick `conport-hermes`, paste cport_live_… key — done
```

A default ConPort agent is auto-created and bound to your Hermes profile in one shot. `hermes conport-hermes init` is only needed to rebind to a different agent.

## What you get

- **Five intent verbs** — `remember` (free thought OR a structured item), `recall` (find anything — cognition + items, one ranked typed list), `create_kind` / `get_kind` (declare and read a structured domain), `event` (log a change on an item). You never pick storage primitives or declare links — ConPort connects by meaning.
- **Structured domains (kinds)** — declare a domain once (`series`, `city`, a research topic) with fields + a status vocabulary; items are the domain's current state, their history is `event`s, a synthesis lives in the item's fields. The schema grows organically — unknown fields are accepted.
- **Auto-bootstrap** — `agent_init` fires at session start; identity + principles + broadcast facts + declared `collections` + mature-community hints + any pending extraction populate the system prompt.
- **Auto-recall** injected before every turn — **multi-strategy** (vector + keyword/FTS + graph-adjacency, fused via Reciprocal Rank Fusion), spanning cognition AND structured items, non-blocking, 2-second budget.
- **Authored loops as skills** — `write_skill` / `get_skill`: keep a reusable procedure as a markdown body in storage with a one-line description for discovery; the body is fetched on demand so it never bloats the session.
- **Typed references between kinds** — declare `refs={field: target_kind}` in `create_kind`; the ref is validated on every write, and `get_referrers` reconstructs exact provenance (a topic's sources), owner-scoped.
- **16 agent tools** — 5 intent verbs + skills (write/get) + refs (get_referrers) + 8 aux (chat-turn / extract-thread / subgraph / entity-delete / event-query / promote-skill / run-start / run-finish).
- **Visibility model** — `private` (the agent's own), `shared` (the owner's agents), `broadcast` (always loaded; crystallized skills + core user facts).
- **Skill emergence** — the backend surfaces `mature_communities`; the agent decides when to crystallize one into a `skill` via `agent_promote_skill`.
- **CLI** — `hermes conport-hermes status | agent | recall | init`.

> **Conversation lands in memory automatically.** Call `agent_chat_turn`
> for every turn; when the response carries `extraction_signal=true`
> (buffer ≥ 10 un-extracted messages), call `agent_extract_thread` with the
> returned `message_ids` to distill the buffer into typed memories.
> See [CHANGELOG](CHANGELOG.md) for the v3-storage → v4-intent migration.

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
[agent calls agent_remember]

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

All tools are wrapped as REST calls under `https://api.conport.app/api/v1`
(intent verbs under `/memory/*`).

### The five intent verbs (the everyday set)

| Tool | Purpose | Prompts that trigger it |
|------|---------|-------------------------|
| `agent_remember` | Keep something. **Free cognition:** `content` + `meta_type` (a thought / fact / observation). **Structured item:** `kind` + `name` + `fields` (the current state of an item in a declared domain). | "Remember that…", "Save this decision…", "Rate this series…" |
| `agent_recall` | Find anything — cognition AND structured items, one ranked typed list (each result has a `type`: `node` or `item`). `scope` filters by `meta_types` / `visibility` / `kind` / `since`–`until`. | "What did we decide about…?", "Which series did I drop?" |
| `agent_create_kind` | Declare a structured domain once (`name`, `fields`, `statuses`) — like creating a table. | "Start tracking cities I'm scoring…" |
| `agent_get_kind` | Read a domain's form (fields + statuses + member count) before writing items. | before `remember(kind=…)` |
| `agent_event` | Log a change / what-happened on an existing item — its append-only timeline (`note` + optional structured `fields`). | "Note that the finale changed my mind on…" |

You never say "node", "entity", "projection", or "link" — connecting things is
ConPort's job (it links by meaning). `remember(kind=…)` into an **undeclared**
kind fails with `unknown_kind` — `create_kind` first. An item is ONE record (a
wishlist is its members filtered by `status`, not a separate item); a
synthesis/verdict lives in the item's `fields`, its history in `event`s.

`agent_init` runs at session start (lifecycle, not a turn-level tool): it
find-or-creates the agent and returns identity / principles / broadcast facts /
declared `collections` / mature-community hints / pending extraction.

### Aux verbs

Beyond the five, a few operations for needs the verbs don't cover:

| Tool | Purpose |
|------|---------|
| `agent_chat_turn` | Buffer one conversation message. When the response returns `extraction_signal=true`, run `agent_extract_thread` next. |
| `agent_extract_thread` | Distill a buffer of messages (`message_ids`) into typed memories. |
| `agent_get_subgraph` | Explore the neighbourhood of a cognition node (pass the `node_id` from a `recall` result of type `node`). |
| `agent_entity_delete` | Delete a structured item (+ its events) by `(kind, name)` — fix a mistake without leaving a duplicate. |
| `agent_event_query` | Read an item's timeline (events aren't in `recall`). Pass the `item_id` from a `recall` result as `entity_id`. |
| `agent_promote_skill` | Crystallize a mature community into a broadcast `skill`. |
| `agent_run_start` / `agent_run_finish` | Wrap a multi-step skill execution for a traceable run record. |

### Two channels to the agent layer

A Hermes agent reaches ConPort's agent layer through exactly one of two
surfaces — both agent-layer only, never the project surface:

1. **This plugin** — REST under `/api/v1/memory/*` + `/api/v1/workspace/*`.
   The default path; no MCP client needed.
2. **MCP** — the same `agent_*` tools at `https://api.conport.app/mcp-agent`
   via the [`conport-agent`](../conport-plugin/skills/conport-agent/SKILL.md)
   skill. Use when your harness speaks MCP rather than REST.

Both accept the same `cport_live_…` key (`Authorization: Bearer` or `X-API-Key`).

**Do not point a Hermes agent at `/mcp`.** That project surface is for
project-shaped IDE consumers (Claude Code, Cursor, Claude.ai chat); exposing
it to a harness agent reintroduces the cross-project recall-hygiene problem the
agent layer was built to avoid (decision-660).

### Recall result shape

`recall` returns one ranked list; each hit carries a `type`:

- **`node`** (free cognition) — `node_id`, `content`, `meta_type` (`identity` /
  `principle` / `fact` / `observation` / `skill` / `artifact`), `visibility`,
  `similarity` (vector cosine; null for keyword-only hits), `score` (the fused
  RRF rank).
- **`item`** (a structured item) — `item_id`, `kind`, `name`, `fields` (the
  item's current-state synthesis), `score`.

`event`s are **not** in recall — they're an item's timeline (read via
`agent_event_query`). Connections between memories are built and traversed by
ConPort internally (entity graph + embeddings); the agent never declares links.

## CLI reference

```bash
hermes conport-hermes status                  # identity + bootstrap counters (identity / principles / broadcast / mature communities / pending extraction)
hermes conport-hermes agent                   # full agent record (JSON)
hermes conport-hermes recall "<query>" [--limit N]   # multi-strategy search over the sphere
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
| Recall returns nothing in fresh session | Brand-new agent — memory is empty | Use `agent_remember` a few times; recall surfaces them once embedded |
| Recall is slow / times out | Network to ConPort exceeds 2s | Bump `recall_timeout_seconds` (but stays non-blocking by design) |
| Tool calls never reach ConPort | Provider deactivated | `hermes memory status` — confirm `conport-hermes` is the active provider |

## FAQ

**Q. How is this different from Hermes' built-in `MEMORY.md`?**
ConPort gives you an intent-driven knowledge base — free cognition AND structured domains (kinds), multi-strategy recall spanning both, emergent skill communities. `MEMORY.md` is a flat append-only file. They can coexist (different tools), but only one `MemoryProvider` is active at a time.

**Q. How does memory get written during a conversation?**
Call `agent_chat_turn` for every turn. When a response returns `extraction_signal=true` (the buffer reached ~10 un-extracted messages), call `agent_extract_thread` with the returned `message_ids` — the backend distills the buffer into typed memories. Explicit knowledge you want saved immediately goes through `agent_remember` directly.

**Q. Can I use ConPort with another MemoryProvider at the same time?**
No — Hermes activates exactly one `MemoryProvider`. You can switch via `hermes memory setup`. (The plain `MEMORY.md` file is a separate mechanism and is unaffected.)

**Q. Where is my API key stored?**
In `$HERMES_HOME/.env` (profile-scoped, never sent anywhere except `api.conport.app`). `conport_provider.json` only holds non-secret config. Rotate any time from the ConPort dashboard.

**Q. Will the agent see my memories from other Hermes profiles?**
No — each Hermes profile binds to one ConPort agent UUID, and ConPort's row-level security scopes memories to the agent/owner. Different profile = different agent = different memory pool.

**Q. Does this work with ConPort self-hosted?**
Yes. Set `api_base_url` to your instance URL during `hermes memory setup`.

## Status

**Alpha.** E2E-validated against production `api.conport.app` — the intent verbs (`/memory/*`), identity wizard, prefetch, and error paths round-trip cleanly.

## Source

This package lives in the [conport-global](https://github.com/shaurgon/conport-global) monorepo under `plugins/conport-hermes/`. File issues there.

## License

MIT
