# conport-hermes — validation report

E2E validation against `hermes-agent v0.12.0` and production `api.conport.app` on 2026-05-02.
Critical-path spike (#2) **passed** — the plugin shows up in `hermes memory setup` once installed
into `$HERMES_HOME/plugins/<name>/`.

## How distribution actually works (correction to original D483)

`hermes plugins install <git-url-or-owner/repo>` clones into `$HERMES_HOME/plugins/<repo-name>/`.
The Python entry-point group `hermes_agent.plugins` is **not** consulted for memory provider
discovery — Hermes scans the filesystem at `<hermes-agent>/plugins/memory/<name>/` (bundled) and
`$HERMES_HOME/plugins/<name>/` (user-installed) and imports `__init__.py` from each. See
`hermes_cli/plugins_cmd.py` and `plugins/memory/__init__.py` in hermes-agent.

Distribution channel for conport-hermes: a `shaurgon/conport-hermes` git mirror, kept in sync
from `plugins/conport-hermes/` in this monorepo (see `.github/workflows/sync-conport-hermes.yml`).
End-user install: `hermes plugins install shaurgon/conport-hermes`.

## Validation results

### Unit / structural (23 pytest checks, all green)

| Layer | Coverage |
|-------|----------|
| `client.py` | recall (GET, query params), remember (POST + payload shape), forget (DELETE + hard flag), reflect (GET + scope), link_memories (correct field names), create_agent (POST with type=worker), 4xx → raise |
| `tools.py` | All 5 schemas registered; dispatcher returns JSON string; never raises on client error; unknown tool returns error JSON |
| Provider lifecycle | `name`, `is_available`, `get_config_schema` shape, `save_config` strips secrets, `initialize` no-op without key, `prefetch` returns string with memories, `prefetch` returns None on error, `handle_tool_call` without identity returns error |
| Setup wizard | reuses existing identity, creates new agent with correct payload |

### Live e2e on Hermes server (production ConPort)

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 1 | Plugin discovered in `~/.hermes/plugins/conport/` | ✅ | Files dropped via filesystem; `hermes plugins install …` will do the same once mirror exists |
| 2 | **Provider in `hermes memory status`** | ✅ **SPIKE PASSED** | "conport (API key / local)" listed alongside bundled providers |
| 3 | `get_config_schema()` returns 4 fields | ✅ | `[api_key, api_base_url, recall_limit, recall_timeout_seconds]` |
| 4 | Identity wizard creates agent | ✅ | POST `/api/v1/agents` 201, persisted to `$HERMES_HOME/conport.json` |
| 5 | `is_available()` toggles on env | ✅ | False without `CONPORT_API_KEY`, True with |
| 6 | `initialize()` reads identity + env | ✅ | Tools active when both present |
| 7 | `prefetch()` injects memories | ✅ | 288 ms; returns formatted plain string per Hermes contract |
| 8 | All 5 tools end-to-end | ✅ | remember 590 ms · recall 337 ms · reflect 92 ms · link <50 ms · forget <50 ms |
| 9 | Error path: bad tool name | ✅ | Returns `{"error": ..., "tool": ...}` JSON |
| 10 | Error path: no identity | ✅ | Tools list empty; handle_tool_call returns clear error JSON |
| 11 | Shutdown closes httpx client | ✅ | No leaked sockets |
| 12 | Test agent + memories cleaned up | ✅ | DELETE `/api/v1/agents/<uuid>` returns 204 |

### Performance

p95 targets met on Hermes server (Amsterdam) → ConPort prod:

| Operation | Latency |
|-----------|---------|
| prefetch (real recall) | 288 ms |
| recall (tool call) | 337 ms |
| remember | 590 ms (incl. embedding) |
| reflect | 92 ms |
| link_memories | <50 ms |
| forget (hard) | <50 ms |

## Contract corrections discovered during e2e

These were applied to `client.py`:

- `recall` returns `{"results": [...]}`, not `{"memories": [...]}`. `_extract_list()` helper now
  handles both keys plus raw arrays (defensive).
- `reflect` is `GET` (not POST), with `scope` ∈ `{day, week, full}` (not `session`/`all`).
- `recall` is `GET` with query param `q` (not POST body `query`).
- `link_memories` uses `source_memory_id`/`target_memory_id`/`relation_type` (not the abridged
  `source_id`/`target_id`/`relationship` from the original task description).

## Deferred

- **Cron daily reflect**: Hermes cron API undocumented in the public guide. Once that surface is
  clear, restore `cron.py` and call `client.reflect(scope="day")` from a registered job.
- **Multi-profile isolation (#13–16)**: not yet exercised, but architecture supports it via
  `$HERMES_HOME` — each profile gets its own `conport.json` → its own agent UUID.
- **Activation in `config.yaml`** for the test server: the e2e ran provider methods directly
  without flipping `memory.provider: conport`, to keep the user's main profile clean. Activation
  is a one-line config write; works the same as bundled providers.

## Reproducible smoke (server-side)

```bash
# inside the Hermes venv
PY=/home/ubuntu/.hermes/hermes-agent/venv/bin/python3

# 1. drop plugin into user dir (later: `hermes plugins install shaurgon/conport-hermes`)
mkdir -p ~/.hermes/plugins/conport
cp /path/to/conport-global/plugins/conport-hermes/conport_hermes/*.py ~/.hermes/plugins/conport/
cp /path/to/conport-global/plugins/conport-hermes/plugin.yaml ~/.hermes/plugins/conport/

# 2. confirm picker
hermes memory status     # 'conport' appears in 'Installed plugins'

# 3. e2e probe — see this repo's tests/ for the script template
$PY -c "
import os; os.environ['CONPORT_API_KEY'] = '<your cport_live_...>'
import sys; sys.path.insert(0, '/home/ubuntu/.hermes/hermes-agent')
from plugins.memory import load_memory_provider
p = load_memory_provider('conport'); print(p.name, p.is_available())
"
```
