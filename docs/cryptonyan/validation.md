# Validation record — 2026-10-21

Environment: Linux cloud sandbox, Python 3.12.14, stock Blender 4.3.2 at `/usr/bin/blender`.
Reference upstream: `e07488212ab7f87c77c8b5792785e57620d61ea0`. Source retrieval was
partial through GitHub, not a full clone. This matters for interpreting discovery counts.

## Executed tests

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s loopcut/tests -p 'test_cryptonyan*.py' -v` (v0.2) | **49 passed**, including 46 portable tests and 3 real Blender headless tests; no Blender skip in this environment. |
| Selected upstream regression modules below | **340 passed**. Dummy local test configuration only; no provider/model requests. |
| MVP discovery on the retrieved subset | Initially 390 tests, 6 errors: two HTTP-server setup errors from forbidden sockets, four upstream workspace tests lacking provider configuration. |
| MVP discovery with the explicit dummy config below | **396 executed, 2 setup errors**: `test_agent_loop.AgentLoopTest` and `test_waves.WaveTest` cannot create their local HTTP servers (`PermissionError: Operation not permitted`). This historical MVP count is not the current total or a passing full-suite claim. |
| `python3 -m compileall -q scripts/addons_core/cryptonyan_asset_studio` | Passed. |
| CLI example `run examples/mission.json` | Completed via mock Codex/Python subprocess; returned task, acceptance result, JSON report and SHA-256 artifact metadata. |
| Core source diff | No changes in `scripts/addons_core/loopcut/` or Blender C++ files. |

Logs: [extension-v2.log](validation/extension-v2.log), [initial extension.log](validation/extension.log), [upstream-regression.log](validation/upstream-regression.log),
[discovery-configured.log](validation/discovery-configured.log), [mock-result.json](validation/mock-result.json).
Intermediate download/missing-fixture errors were resolved before recording the final
regression results. The entire upstream test tree was not retrieved; 340 is the selected
regression set, not the total upstream suite. Native UI and real Codex execution were not run.

The Codex CLI present here is 0.163.0. Its experimental JSON schema was generated
successfully and checked for `thread/start`, `turn/start`, dynamic tools and account
metadata. A real `probe-codex` attempt exited before the handshake: the CLI's normal
home is read-only in this sandbox (`Read-only file system`). No credentials were
copied, no sign-in was attempted and no model turn was started. Protocol execution
is tested with an actual scripted subprocess, including early notifications, scope
rejection, idempotence, missing authentication, malformed responses and cancellation.
One of the three Blender tests now exercises scripted Codex -> actual Blender ->
measured quality retrieval. The MCP CLI is also exercised by a separate stdio client.

Exact successful upstream regression command (from repository root):

```sh
PYTHONPATH=loopcut/tests \
LOOPCUT_API_KEY=test-only LOOPCUT_BASE_URL=http://127.0.0.1:9/v1 LOOPCUT_MODEL=test \
python3 -m unittest \
  test_codex_app test_glb test_object_info test_scene_diff test_orchestrator \
  test_ownership_rules test_texture_tools test_uv_tools test_worker_ipc test_workspace
```

The dummy key is a literal test fixture, not a credential. No service exists at that
local port; these modules mock external interactions. The Codex "could not resume
thread gone" message is an expected scripted failure-path diagnostic, not a live call.

The configured discovery command was:

```sh
LOOPCUT_API_KEY=test-only LOOPCUT_BASE_URL=http://127.0.0.1:9/v1 LOOPCUT_MODEL=test \
python3 -m unittest discover -s loopcut/tests
```

## Covered behaviors

- Strict schema/defaults/roundtrip, invalid types/nonfinite budgets, state transitions.
- Windows/Unix traversal forms, symlinks, output escape, artifact tampering, input hashes.
- Persistent JSON task records in SQLite, revision linkage, exclusive service ownership,
  interrupted recovery, bounded concurrency and queue capacity.
- Queued and running cancellation, actual child termination on cancellation/timeout,
  bounded retries and shared time budget, sanitized errors and credential-free child env.
- Fixture reports, invalid/degenerate/duplicate faces, open/closed edge topology,
  triangle budgets, repair guards, nonfinite data, complexity limits and spoof rejection.
- MCP initialization, tool listing, submit/result, malformed input and notifications.
- Multi-input audit and source changes after snapshot.
- Blender source-file hashes unchanged after dry run and opt-in repairs; known cube
  counts/world bounds; reuse of Loopcut UV metrics; independent copy mesh data; unchanged
  vertex coordinates/transforms; modifiers/shape keys guarded; saved output reopened;
  quaternion rotation reported as actual Euler orientation.

## Required local validation (not completed here)

### Windows + actual Loopcut Blender 5.2.2

Use the PowerShell installation commands in [README.md](README.md), point
`LOOPCUT_BLENDER` to the actual `blender.exe`, then run:

```powershell
py -3.13 -m unittest discover -s loopcut/tests -p 'test_cryptonyan*.py' -v
py -3.13 -m unittest discover -s loopcut/tests
```

Use the full checkout for the second command. Run on a machine permitting local
HTTP sockets; provide the project's normal **test** setup if workspace configuration
tests need it. Do not use production keys for the unit suite. Specifically verify Windows file locking,
long/Unicode paths, process-tree termination via `taskkill /T`, timeout while Blender
is inside native work, no worker left after normal cancellation, and a second service
refusing the same workspace. The added Windows/Linux Python 3.11/3.13 workflow
runs on publication; consult the pull request checks for its current results.

Run representative meshes (including cat rigs, animation/drivers, linked data,
modifiers, negative scale, large UV sets and shape keys). Reports must label guarded
or skipped operations. Open returned repaired scenes and compare world geometry,
material bindings and original objects. Pack external dependencies first; the MVP
does not make linked libraries/textures/caches portable.

### Claude Code and Codex

Configure the documented stdio server and exercise all five tools in an actual Claude
Code session. Test cancellation then revision, restart and result retrieval. Validate
the installed client's supported MCP protocol. Run `probe-codex`, then one small
mission using the experimental adapter and the user's normal Codex sign-in, as detailed
in [codex-adapter.md](codex-adapter.md). Real authenticated dispatch has not been
validated here. The current native Loopcut Codex app-server explicitly disables
configured MCP servers; the new adapter is independent of that live UI loop.

### Unreal Engine 5.8

No Unreal executable or editor session was available. The adapter is only a typed
contract: there is **no import command to validate yet**. The next implementation must
first probe the installed 5.8 editor/plugin versions, then import one known fixture to
a new `/Game/CryptoNyan/Review/...` path and verify units, axes, geometry counts/bounds,
material assignments, LODs, collisions and sockets without overwrites. Rig/skeleton,
quadruped animation/root motion and in-editor runner survivability require dedicated
fixtures and acceptance tests. No UE compatibility is inferred from Blender tests.

### ComfyUI, RTX 5080 and visual quality

No ComfyUI endpoint, model/workflow, CUDA rendering or RTX 5080 benchmark was run.
Check actual workflow schemas and license provenance before adapter implementation.
Validate generated output hashes and staging paths, then benchmark VRAM/latency on the
local GPU. Visual before/after captures remain a contract for wrapping Loopcut's
existing inspection pipeline; no render comparison or aesthetic score was fabricated.

## Publication

The first GitHub run passed both Linux extension jobs. Windows exposed two test
portability assumptions: temporary-directory 8.3 aliases and an exact retry count
based on a 50 ms OS wait. The path assertion now compares canonical roots; the retry
test uses a controlled execution clock and verifies that attempts share one deadline.
Runtime path checks and deadline enforcement are unchanged. Consult PR checks for
the subsequent run, including the full upstream suite on a complete checkout.

Remote branch creation succeeded after the user updated the GitHub integration
permissions. The feature branch is `feat/cryptonyan-mission-bridge-asset-doctor`;
its review description is [pull-request.md](pull-request.md). Publication preserves
upstream history and adds only the feature files. No merge or release is performed.
