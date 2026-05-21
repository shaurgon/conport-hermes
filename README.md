# conport-hermes

ConPort memory provider for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — long-term knowledge graph for autonomous agents on top of ConPort's Agent Memory v2 tree (decisions 660–682).

```bash
hermes plugins install shaurgon/conport-hermes
hermes memory setup     # pick `conport-hermes`, paste cport_live_… key — done
```

A default ConPort agent is auto-created and bound to your Hermes profile in one shot. `hermes conport-hermes init` is only needed to rebind to a different agent.

## What you get

- **Tree-shaped persistent memory** — trunk + identity / principles / person-knowledge sub-stores + branches per task / topic (doc-91)
- **Auto-bootstrap** — `agent_init` fires at session start; trunk roots + counters populate the system prompt
- **Auto-recall** injected before every turn — composite-scored (0.6·cosine + 0.2·recall_factor + 0.2·foundational_boost), non-blocking, 2-second budget
- **31 agent_* tools** — write/read/reflect, tree navigation, branch lifecycle, artifacts, lift candidates, promotion conflicts, skill versioning + notes + activations
- **Non-destructive gravity** — no `forget`; consolidation + supersession happen via tree edges and re-crystallization
- **CLI** — `hermes conport-hermes status | agent | init | reflect | branches | tail`

> **v1.0.0 — Agent Memory v2 (breaking).** The flat v1 memory surface
> (`conport_remember` / `conport_recall` / `conport_forget` /
> `conport_reflect` / `conport_link_memories`) is gone. Backend data
> already migrated on 2026-05-20 (task-319) — every memory lives in
> the new tree shape, indexed under the user's existing
> `person_knowledge_root` until gravity reshapes it. Client-side
> migration: pull the new plugin version, restart Hermes; first
> `agent_init` returns `bootstrap_state='continuing'` and you're set.
> Code that called the v1 verbs needs to rewrite to `agent_remember` /
> `agent_recall`. See [CHANGELOG](CHANGELOG.md) for the full
> verb-by-verb diff.

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

### Writes / reads (the everyday set)

| Tool | Purpose | Prompts that trigger it |
|------|---------|-------------------------|
| `agent_remember` | Persist a fact, decision, lesson. `parent_id` null → backend routes via argmax similarity (decision-673). | "Remember that…", "Save this decision…", "Note for future me…" |
| `agent_recall` | Composite-scored search across the tree. `scope_root_id` narrows to one sub-store. | "What did we decide about…?", "Have we discussed X before?" |
| `agent_reflect` | Manual gravity on a node: persist merged content + consolidation + crystallisation. Backend never synthesises (decision-692). | "Consolidate this branch", "Re-distil today's thread" |

### Tree navigation

| Tool | Purpose |
|------|---------|
| `agent_get_node` | One node + immediate children |
| `agent_list_branches` | Branches filtered by `state` (active / dormant / closed) |
| `agent_walk_branch` | Full branch arc + linked artifacts |

### Branch lifecycle

`agent_create_branch`, `agent_close_branch`, `agent_activate_node`, `agent_activate_branch` (decision-680).

### Artifacts

`agent_emit_artifact`, `agent_list_artifacts`, `agent_get_artifact`, `agent_artifact_provenance`, `agent_node_artifacts`. Artifacts don't participate in gravity (decision-664) — use them for branch outputs.

### Cross-pollination + promotion

`agent_review_lift_candidates`, `agent_confirm_lift`, `agent_request_synthesis_assistance` (decisions 670–672).
`agent_review_promotion_conflicts`, `agent_resolve_promotion_conflict` (decisions 671 + 692).

### Skills

`agent_load_skill`, `agent_list_skills`, `agent_skill_versions`, `agent_get_skill_version`, `agent_get_skill_md`, `agent_skill_notes`, `agent_add_skill_note`, `agent_supersede_skill_note`, `agent_complete_re_crystallization`, `agent_review_re_crystallization`, `agent_skill_activations` (decisions 663 / 675 / task-356).

### Removed in v1.0.0

| Old verb | Replacement |
|----------|-------------|
| `conport_remember` | `agent_remember` (parent_id is optional — auto-routing) |
| `conport_recall` | `agent_recall` (composite scoring, scope_root_id) |
| `conport_forget` | **No replacement.** Gravity is non-destructive (decision-667); consolidation + supersession at re-crystallization is the path. |
| `conport_reflect` | `agent_reflect(node_id, new_content)` — per-node, scoped |
| `conport_link_memories` | **No replacement.** Tree edges (`parent_id`) + trunk promotion provenance replace explicit links. |

### Project tools — removed in v0.6.0

Earlier versions exposed a project-shaped surface (`conport_attach_project`,
`conport_search`, `conport_add_task`, `conport_sync_decision`,
`conport_log_progress`, document tools, block tools — 14 tools total).
Removed in v0.6.0 per decision-660: harness agents work in continuous
conversation streams with dozens of context switches per day, not
project-shaped tasks. The "currently attached project" pattern is
incompatible with that runtime.

A Hermes agent reaches ConPort via exactly two channels — both
agent-layer only, never the project surface:

1. **This plugin** — the five `conport_*` tools above, REST under the
   hood. Default path.
2. **`/mcp-agent`** — the 29 `agent_*` tools at
   `https://api.conport.app/mcp-agent` via the
   [`conport-agent`](../conport-plugin/skills/conport-agent/SKILL.md) skill.
   Use when you specifically want the richer v2 surface (branches,
   skill versioning, lift candidates, …) instead of the v1 memory
   API this plugin wraps.

Both channels accept the same `cport_live_…` key (`Authorization: Bearer`
or `X-API-Key`).

**Do not point a Hermes agent at `/mcp`.** The project surface is for
project-shaped IDE consumers (Claude Code, Cursor, Claude.ai chat);
exposing it to a harness agent reintroduces exactly the cross-project
recall hygiene problem v0.6.0 was meant to fix (decision-660).

### Node shape

Every node in the tree is one record with:

- **`id`** — per-agent integer
- **`content`** — free-form text (≤10 000 chars)
- **`parent_id`** — anchors the node in the tree (null only for the
  trunk root). Auto-routing on `agent_remember` picks the right
  ancestor by embedding similarity (decision-673).
- **`branch_id`** — the origin id this node belongs to (null for
  trunk-resident nodes).
- **`is_skill`** — `true` once gravity crystallises the node (decision-663).
- **`tags`** — free-form list; used for filtering, not for routing.

Recall hits carry an additional **`composite_score`** (0..1) per
decision-678: `0.6·cosine + 0.2·recall_factor + 0.2·foundational_boost`.

### Tree edges

Edges are structural (`parent_id`) and bookkeeping
(`branch_id`, `lifted_to_trunk_node_id`, `lift_source_origin_ids`).
There is no separate "link relation" type any more — supersession
and cross-branch lift are expressed through these fields plus the
re-crystallisation history on skills.

## CLI reference

```bash
hermes conport-hermes status                                 # identity + bootstrap state + counters
hermes conport-hermes agent                                  # full agent record (JSON)
hermes conport-hermes reflect --node-id N [--new-content STR]  # manual gravity on one node
hermes conport-hermes branches [--state active|dormant|closed]
hermes conport-hermes tail [--interval 2]                    # poll active branches
hermes conport-hermes init                                   # (re)run the identity wizard
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
ConPort gives you a tree-shaped knowledge graph with composite-scored recall, branches per topic, crystallised skills, and cross-pollination. `MEMORY.md` is a flat append-only file. They can coexist (different tools), but only one `MemoryProvider` is active at a time.

**Q. What happens when reflect runs?**
`agent_reflect(node_id, new_content?)` operates on a single node. With `new_content` — backend persists the merged content, refreshes the embedding, runs the consolidation pass, and checks whether the node now meets the skill-crystallisation threshold (decision-663). Without — pure bookkeeping. Backend never synthesises; the agent provides the merged content (decision-692).

**Q. Can I use ConPort with another MemoryProvider at the same time?**
No — Hermes activates exactly one `MemoryProvider`. You can switch via `hermes memory setup`. (The plain `MEMORY.md` file is a separate mechanism and is unaffected.)

**Q. Where is my API key stored?**
In `$HERMES_HOME/.env` (profile-scoped, never sent anywhere except `api.conport.app`). `conport_provider.json` only holds non-secret config. Rotate any time from the ConPort dashboard.

**Q. Will the agent see my memories from other Hermes profiles?**
No — each Hermes profile binds to one ConPort agent UUID, and ConPort's row-level security scopes memories to the agent. Different profile = different agent = different memory pool.

**Q. Does this work with ConPort self-hosted?**
Yes. Set `api_base_url` to your instance URL during `hermes memory setup`.

## Background consolidation

v1.0.0 no longer has a `--scope` wide reflect — gravity runs per-node
(`agent_reflect(node_id, new_content?)`) and the backend's APScheduler
jobs handle the cross-cutting passes (cross-pollination scan, promotion
threshold check, re-crystallisation hysteresis) on their own cadence.
If you want a daily nudge to surface the lift queue / promotion
conflicts to the user, a thin status cron works:

```cron
# crontab -e
0 3 * * * /home/USER/.hermes/hermes-agent/venv/bin/hermes conport-hermes status > /tmp/conport-status.log 2>&1
```

## Status

**Alpha** (v0.1.4). E2E-validated against `hermes-agent v0.12.0` and production `api.conport.app` — all five tools, identity wizard, prefetch, error paths, and shutdown round-trip cleanly. See [VALIDATION.md](VALIDATION.md) for the full report.

## Source

This package lives in the [conport-global](https://github.com/shaurgon/conport-global) monorepo under `plugins/conport-hermes/`. File issues there.

## License

MIT
