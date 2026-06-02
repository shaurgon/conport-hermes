# conport-hermes

ConPort memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — a long-term knowledge graph for autonomous agents on top of ConPort's **Agent Memory v3 sphere graph** + **Workspace v1** (event-sourced records).

```bash
hermes plugins install shaurgon/conport-hermes
hermes memory setup     # pick `conport-hermes`, paste cport_live_… key — done
```

A default ConPort agent is auto-created and bound to your Hermes profile in one shot. `hermes conport-hermes init` is only needed to rebind to a different agent.

## What you get

- **Sphere-graph memory** — every memory is a typed node (`identity` / `principle` / `fact` / `observation` / `skill` / `artifact`) connected to others by typed edges (`semantic` / `derived_from` / `temporal` / `skill_of` / `competing_view` / `supersedes`). No tree, no `parent_id`, no branches — topics emerge as dense edge clusters.
- **Auto-bootstrap** — `agent_init` fires at session start; identity + principles + broadcast facts + mature-community hints + any pending extraction populate the system prompt.
- **Auto-recall** injected before every turn — **multi-strategy** (vector + keyword/FTS + graph-adjacency, fused via Reciprocal Rank Fusion), non-blocking, 2-second budget.
- **17 agent tools** — 6 memory (remember / recall / chat-turn / extract-thread / subgraph / promote-skill) + 11 workspace (entities / events / runs / projections / node-entity links).
- **Visibility model** — `private` (the agent's own), `shared` (the owner's agents), `broadcast` (always loaded; crystallized skills + core user facts).
- **Skill emergence** — the backend surfaces `mature_communities`; the agent decides when to crystallize one into a `skill` node via `agent_promote_skill`.
- **CLI** — `hermes conport-hermes status | agent | recall | init`.

> **Conversation lands in memory automatically.** Call `agent_chat_turn`
> for every turn; when the response carries `extraction_signal=true`
> (buffer ≥ 10 un-extracted messages), call `agent_extract_thread` with the
> returned `message_ids` to distill the buffer into typed nodes + edges.
> See [CHANGELOG](CHANGELOG.md) for the v2-tree → v3-sphere migration.

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
(sphere memory under `/sphere/*`, workspace under `/workspace/*`).

### Memory (the everyday set)

| Tool | Purpose | Prompts that trigger it |
|------|---------|-------------------------|
| `agent_remember` | Persist a typed node (`meta_type` + `content`), optionally with edges to existing nodes. | "Remember that…", "Save this decision…", "Note for future me…" |
| `agent_recall` | Multi-strategy search (vector + keyword/FTS + graph adjacency, RRF-fused). `scope` filters by `meta_types` / `visibility` / `community_id` / `since`–`until`. | "What did we decide about…?", "Have we discussed X before?" |
| `agent_chat_turn` | Buffer one conversation message. When the response returns `extraction_signal=true`, run `agent_extract_thread` next. | called for every turn |
| `agent_extract_thread` | Distill a buffer of messages (`message_ids`) into typed nodes + edges. | fired by `extraction_signal` |
| `agent_get_subgraph` | BFS outward from a node through typed edges, respecting visibility. | "What else is connected to this topic?" |
| `agent_promote_skill` | Crystallize a mature community into a `skill` node (broadcast). | when `agent_init` surfaces a mature community worth promoting |

`agent_init` runs at session start (lifecycle, not a turn-level tool): it
find-or-creates the agent and returns identity / principles / broadcast facts
/ mature-community hints / pending extraction.

### Workspace (event-sourced records)

Structured, append-only records that live **beside** memory (never mixed into
the sphere graph): `agent_entity_upsert` / `agent_entity_get` /
`agent_entity_list`, `agent_event_record` / `agent_event_query`,
`agent_run_start` / `agent_run_finish`, `agent_projection_record` /
`agent_projection_current` / `agent_projection_history`, and
`agent_link_node_to_entity` (cross-link a memory node to a workspace entity).
Use the workspace for facts that need exact queries, history, or run lineage
— not for free-form recall.

### Two channels to the agent layer

A Hermes agent reaches ConPort's agent layer through exactly one of two
surfaces — both agent-layer only, never the project surface:

1. **This plugin** — REST under `/api/v1/sphere/*` + `/api/v1/workspace/*`.
   The default path; no MCP client needed.
2. **MCP** — the same `agent_*` tools at `https://api.conport.app/mcp-agent`
   via the [`conport-agent`](../conport-plugin/skills/conport-agent/SKILL.md)
   skill. Use when your harness speaks MCP rather than REST.

Both accept the same `cport_live_…` key (`Authorization: Bearer` or `X-API-Key`).

**Do not point a Hermes agent at `/mcp`.** That project surface is for
project-shaped IDE consumers (Claude Code, Cursor, Claude.ai chat); exposing
it to a harness agent reintroduces the cross-project recall-hygiene problem the
agent layer was built to avoid (decision-660).

### Node shape

Every memory is one `harness_node` record:

- **`id`** — per-agent integer
- **`meta_type`** — `identity` / `principle` / `fact` / `observation` / `skill` / `artifact`
- **`content`** — free-form text (≤10 000 chars)
- **`visibility`** — `private` / `shared` / `broadcast` (identity + principle are always `private`)
- **`created_by_agent_uuid`** — provenance
- **`frozen_community_id`** — the Louvain community a node settled into (null until detection runs)
- **`tags`** — free-form list; used for filtering

Recall hits additionally carry **`similarity`** (vector cosine; null for
keyword-only hits) and **`score`** (the fused RRF score the result was ranked
by).

### Edges

Edges are typed `harness_edge` rows: `source_node_id`, `target_node_id`,
`edge_type` (one of the six relationship kinds above) and `weight`. Supersession
and cross-references are explicit edges — there is no structural `parent_id`.

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
ConPort gives you a sphere-graph knowledge base with multi-strategy recall, typed edges, emergent skill communities, and a separate event-sourced workspace. `MEMORY.md` is a flat append-only file. They can coexist (different tools), but only one `MemoryProvider` is active at a time.

**Q. How does memory get written during a conversation?**
Call `agent_chat_turn` for every turn. When a response returns `extraction_signal=true` (the buffer reached ~10 un-extracted messages), call `agent_extract_thread` with the returned `message_ids` — the backend distills the buffer into typed nodes + edges. Explicit knowledge you want saved immediately goes through `agent_remember` directly.

**Q. Can I use ConPort with another MemoryProvider at the same time?**
No — Hermes activates exactly one `MemoryProvider`. You can switch via `hermes memory setup`. (The plain `MEMORY.md` file is a separate mechanism and is unaffected.)

**Q. Where is my API key stored?**
In `$HERMES_HOME/.env` (profile-scoped, never sent anywhere except `api.conport.app`). `conport_provider.json` only holds non-secret config. Rotate any time from the ConPort dashboard.

**Q. Will the agent see my memories from other Hermes profiles?**
No — each Hermes profile binds to one ConPort agent UUID, and ConPort's row-level security scopes memories to the agent/owner. Different profile = different agent = different memory pool.

**Q. Does this work with ConPort self-hosted?**
Yes. Set `api_base_url` to your instance URL during `hermes memory setup`.

## Status

**Alpha.** E2E-validated against production `api.conport.app` — sphere memory (`/sphere/*`) and workspace (`/workspace/*`) endpoints, identity wizard, prefetch, and error paths round-trip cleanly.

## Source

This package lives in the [conport-global](https://github.com/shaurgon/conport-global) monorepo under `plugins/conport-hermes/`. File issues there.

## License

MIT
