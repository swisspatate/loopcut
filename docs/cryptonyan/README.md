# CryptoNyan Asset Studio MVP

An opt-in mission bridge and Asset Doctor for CryptoNyanRun. It queues local asset
audits, runs isolated workers, persists results and offers MCP tools for an external
orchestrator. It does not alter Loopcut's native agent behavior.

Read [architecture.md](architecture.md), [validation.md](validation.md) and
[roadmap.md](roadmap.md). The animation and visual QA modules
are **contracts only**, not working integrations.

Version 0.8 adds [combined Blender world previews and geometry QA](world-preview.md):
shared meshes, per-instance biome materials, zone collections, a common animation
window, static/swept overlap diagnostics and connector checks. Geometry checks do
not certify Unreal collision or controller behavior.

Version 0.7 adds [world assembly and Unreal runtime review](world-runtime.md): connect
audited kits at matching ground-centre sockets, assign biome palettes, scatter off-track
posts, generate periodic PBR maps and place a world through a new Unreal actor/plugin.
Blender and portable paths are tested; the full UE plugin build and runtime require local acceptance.

Version 0.6 adds [layered paths, cyclic lifts and material themes](worlds-and-themes.md):
upper/lower side branches, actual Blender preview animation, explicit Unreal motion
tracks and audited asset-by-theme batch publications. Static route checks exclude
moving branches; the actual Unreal gameplay behavior still requires local acceptance.

Version 0.5 adds the [Runner module kit](runner-kit.md): seeded flat three-lane layouts,
analytical jump windows with landing/recovery propagation, seed scans, SVG review,
Blender module/preview generation, audited GLB publication and a neutral Unreal/PCG CSV.
General PCGEx graphs and actual character-controller validation remain local/future work.

Version 0.4 adds the [PBR and ComfyUI pipeline](material-pipeline.md): a local HTTP
client, durable generation receipts, Material Doctor bundles, material application to
a new Blender copy and GLB publication with embedded PNGs. Real Blender export/reimport
is tested; live GPU generation and Unreal textured import remain local acceptance work.

Version 0.3 adds [Asset Publisher](publisher.md): a real Blender static mesh export,
portable checked GLB/manifest, and an explicit local Unreal review importer. Blender
export/roundtrip is tested; Unreal execution still requires local UE 5.8 validation.

Version 0.2 introduced an experimental [local Codex app-server adapter](codex-adapter.md),
a no-model `probe-codex` command and real stdio client/server lifecycle tests. Its
wire protocol is verified against the generated CLI 0.163.0 schema and scripted
peers; an authenticated model turn still requires local validation.

## Run the complete mock example

From a complete Loopcut checkout, Python 3.11+; no pip installation, model account,
API key or Blender required for the mock:

```sh
export PYTHONPATH="$PWD/scripts/addons_core"
python3 -m cryptonyan_asset_studio \
  --workspace /tmp/cryptonyan-jobs \
  --asset-root docs/cryptonyan/examples/assets \
  run docs/cryptonyan/examples/mission.json
```

The result includes a durable task ID, per-input report, acceptance result and artifact
hashes. The fixture is an intentionally open triangle, so boundary edges are a warning.
This is a Claude-style structured mission through a **mock** Codex executor; no model ran.

```sh
python3 -m cryptonyan_asset_studio --workspace /tmp/cryptonyan-jobs show TASK_ID
python3 -m unittest discover -s loopcut/tests -p 'test_cryptonyan*.py' -v
```

Tests use temporary directories. Blender tests explicitly skip if `blender` is absent;
set `LOOPCUT_BLENDER` to test the actual Loopcut executable. No native C++ build is needed.

## Windows installation and headless use

Keep the full source checkout, including `scripts/addons_core/loopcut` (the reused inspectors).
This MVP is a Python package/CLI, not an add-on ZIP to install via Blender Preferences.
In PowerShell from the checkout:

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$env:LOOPCUT_BLENDER = 'C:\Tools\Loopcut\blender.exe' # set your actual executable
py -3.13 -m unittest discover -s loopcut/tests -p 'test_cryptonyan*.py' -v

py -3.13 -m cryptonyan_asset_studio `
  --workspace "$env:LOCALAPPDATA\CryptoNyanAssetStudio\jobs" `
  --asset-root .\docs\cryptonyan\examples\assets `
  run .\docs\cryptonyan\examples\mission.json
```

For your own **saved, self-contained** scene, create `mission.json`:

```json
{
  "inputs": ["cat.blend"],
  "target_assets": ["CatBody"],
  "constraints": {"timeout_seconds": 120, "max_attempts": 1, "repair_copy": false},
  "success_criteria": {"max_triangles": 50000, "allow_warnings": true}
}
```

```powershell
py -3.13 -m cryptonyan_asset_studio `
  --workspace "$env:LOCALAPPDATA\CryptoNyanAssetStudio\jobs" `
  --asset-root 'D:\CryptoNyan\AssetsToAudit' `
  --executor blender --blender "$env:LOOPCUT_BLENDER" run .\mission.json
```

Omit `target_assets` to inspect all scene objects. The same targets apply to every input
in a multi-file mission; missing targets fail explicitly. `repair_copy: true` permits
only copying/naming/organization of unguarded meshes, returning `repaired-N.blend` in
the task directory. Source objects and files are never replaced. Inspect the report
and returned scene before using a copy. Repaired scenes contain originals **and** copies.

Audit every matching file directly in an input directory (non-recursive):

```powershell
py -3.13 -m cryptonyan_asset_studio `
  --workspace "$env:LOCALAPPDATA\CryptoNyanAssetStudio\batch" `
  --asset-root 'D:\CryptoNyan\AssetsToAudit' `
  --executor blender --blender "$env:LOOPCUT_BLENDER" --workers 2 batch
```

Without `--executor blender`, batch processes `.json` fixtures. `--repair-copy` is
available on batch but is rejected by the mock executor. CLI exit codes: 0 = audit
completed and criteria passed; 1 = worker failure or failed asset criteria; 2 = setup
or input error. Cancellation/control of running missions uses the long-lived MCP service.

## Explicit local MCP configuration

The stdio server opens **no TCP listener**. Configure it in the external MCP client
(for example Claude Code), adapting all paths to your checkout:

```json
{
  "mcpServers": {
    "cryptonyan-assets": {
      "command": "C:\\Python313\\python.exe",
      "args": [
        "-m", "cryptonyan_asset_studio",
        "--workspace", "C:\\CryptoNyan\\jobs",
        "--asset-root", "D:\\CryptoNyan\\AssetsToAudit",
        "--executor", "blender",
        "--blender", "C:\\Tools\\Loopcut\\blender.exe",
        "serve"
      ],
      "env": {"PYTHONPATH": "C:\\src\\loopcut\\scripts\\addons_core"}
    }
  }
}
```

Use the mock executor and fixture asset directory for a first client check. Stdio
authorization is the local user's explicit launch and access to the configured roots.
Do not expose stdio via an unauthenticated network relay. Any future HTTP transport
must default to loopback and implement authentication/authorization before network use.
Real Claude Code interoperability is pending; protocol request/response paths are tested.

| Tool | Arguments | Behavior |
| --- | --- | --- |
| `mission_submit` | `mission` object | Validate, snapshot, queue; returns a task ID immediately after snapshots. |
| `mission_query` | `task_id` | Read state, attempts, timestamps, error and artifact metadata. |
| `mission_cancel` | `task_id` | Idempotent cancellation; await `cancelled` for a running task. |
| `mission_revise` | `task_id`, complete `mission` | Terminal task only; creates a new ID linked to its predecessor. |
| `mission_result` | `task_id` | Completed task only; verifies artifact hashes before returning JSON. |

The client should poll at a modest interval (e.g. one second), stop on a terminal state,
and inspect `quality_passed`, not just `state`. Closing stdin shuts down the service
and cancels outstanding jobs. Records remain available through `show` and the Python API.
Only one service may own a workspace; use separate workspaces for independent sessions.

Enabling `LOOPCUT_CODEX_APP` and native orchestration together does not connect these
tools. Upstream explicitly disables the user's MCP servers in its Codex app-server
command. The independent adapter uses explicit dynamic-tool dispatch and the user's
normal Codex sign-in. The adapter described in
[codex-adapter.md](codex-adapter.md) implements that narrow mission dispatch outside
the live Loopcut UI. No undocumented Codex Cloud API is used here.

## Python adapter API

```python
from cryptonyan_asset_studio.bridge import MissionBridge
from cryptonyan_asset_studio.executors import MockCodexExecutor

with MissionBridge('/tmp/crypto-jobs', '/path/to/fixture-assets', MockCodexExecutor()) as bridge:
    task = bridge.submit({'inputs': ['triangle.json']})
    state = bridge.wait(task['id'], timeout=30)
    result = bridge.result(task['id'])  # raises if execution did not succeed
```

`CodexExecutor` specifies the seam implemented by the experimental `CodexAppServerExecutor`.
Implementations must honor deadlines/cancellation and write only inside their assigned
attempt directory. Built-in workers receive no model credentials and run only the
fixed Asset Doctor entry point. The SQLite database is the authoritative durable task
record; `Store.events(task_id)` returns structured, secret-free lifecycle events.

Keep input/workspace directories private. Process isolation and path checks do not
make untrusted Blender files or third-party plugins safe to execute. This MVP disables
auto-execution, uses factory startup, and does not run arbitrary mission-supplied code.
