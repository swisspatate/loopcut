# Validation record — 2026-10-21

For the consolidated Windows/local acceptance checklist, see
[Checklist des validations sur ton PC](local-pc-checklist.md).
This file retains the cloud test evidence and historical milestone records.

Environment: Linux cloud sandbox, Python 3.12.14, stock Blender 4.3.2 at `/usr/bin/blender`.
Reference upstream: `e07488212ab7f87c77c8b5792785e57620d61ea0`. Source retrieval was
partial through GitHub, not a full clone. This matters for interpreting discovery counts.

## Executed tests

Version 0.15 adds [asset-bound texture collections](texture-collections.md). Local
extension discovery before the final Windows filename portability adjustment:
**296 cases in 281.274s, 293 passed and three sandbox socket skips**. All 20 existing
Blender tests and both compiled C++ checks passed. See
[collections-extension.log](validation/collections-extension.log).
The adjustment prefixes intent filenames to support Windows reserved identifiers
such as `con` and `nul`, and adds a regression case. Final focused suite:
**22 cases in 3.214s, 21 passed and one sandbox socket skip**; see
[collections-final.log](validation/collections-final.log). The resulting complete
extension suite contains 297 cases; final Windows/Linux CI results are in the PR.

Collection coverage includes deterministic prompts/seeds/IDs, immutable offline
plans, source/profile/descriptor drift, preflight gates, durable intentions and
interruption recovery, uncertain submissions, one outstanding request per collection,
foreign ownership rejection, candidate/index corruption, bounded plans, existing
CLI execution and a real stdio/HTTP multi-job acceptance test. That HTTP test is
mandatory in CI and uses scripted PNG outputs, not a GPU model. No actual artistic
consistency, ComfyUI model loading, UV match, Unreal assignment or VRAM result is
certified here; use the central PC checklist for those validations.

Version 0.14 adds [read-only ComfyUI preflight](comfy-preflight.md). Final local
extension discovery: **275 cases in 270.500s, 273 passed and two sandbox socket
tests skipped**. All 20 existing Blender tests and both compiled C++ tests pass.
Log: [comfy-preflight-extension.log](validation/comfy-preflight-extension.log).
The 17 new cases cover metadata/graph checks, effective prompt/seed fingerprints,
missing nodes/model choices, custom schema uncertainty, bounded diagnostics,
malformed/oversized responses, read-only MCP behavior and actual CLI/stdio HTTP
wiring. The last test cannot bind a socket in this sandbox; it is mandatory in CI
(an inability to bind there fails rather than skips). Scripted HTTP metadata is
not a real ComfyUI installation, GPU inference or model-loading validation. Final
Windows/Linux CI results are recorded in the feature PR.

The first Windows 3.11 CI run exposed a test portability issue: its file-content
snapshot tried to read the active owner-lock byte through a second handle, which
Windows correctly rejects. [Failure excerpt](validation/comfy-preflight-windows-initial-failure.log).
The test now compares lock size/mtime and all other file bytes while the lock stays
held. Runtime locking and diagnostic behavior are unchanged. The final focused
run has **17 cases, 16 passed and one sandbox socket skip**; see
[comfy-preflight-final.log](validation/comfy-preflight-final.log). The full local
log above precedes this test-only fix; CI reruns the final commit on both platforms.

Version 0.13 adds [Unreal inspection and material variants](unreal-material-variants.md).
The **19 new tests pass in 1.932s**; full local discovery reports **258 cases in
197.340s: 257 passed, one sandbox socket skip**, including all 20 existing Blender
tests and both compiled C++ tests. Logs: [targeted](validation/unreal-material-targeted.log)
and [extension](validation/unreal-material-extension.log).

The initial PR #13 CI head passed the 19 new tests on all four OS/Python jobs and
the full repository suite (**2,725 cases, 129 skipped**). Windows Python 3.13 then
hit the existing elemental-rules C++ test's 30-second MinGW compilation deadline.
The [failure excerpt](validation/unreal-material-windows-initial-failure.log) is
retained. Compilation now allows 120 seconds on Windows, retaining 30 seconds on
Linux, the separate 10-second executable deadline and every C++ assertion. Final
CI results for this adjustment are recorded in PR #13.

The new tests inject a scripted Unreal module. They exercise actual material-bundle
validation, inspection/plan receipts, filesystem fingerprints and sidecars, CLI dry-run,
MCP plan wiring, ownership, source drift before/during imports, inherited parameter
readback, normal import settings, one-slot preview copies, skeleton references, forbidden
overwrites and retained partial failures. No Unreal executable, package compiler,
shader compiler or GPU model is run by these tests. The preview duplication, shader
samplers, texture settings after reload and visual behavior require UE 5.8.3 acceptance
on the user's machine; passing mocks do not establish those results.

Version 0.12 adds [existing-project discovery and asset-bound texture requests](existing-project.md).
Local regression discovery reports **239 cases in 175.910s: 238 passed, one socket
test skipped** by the sandbox. All 20 existing Blender tests and both compiled C++
tests passed. Log: [existing-project-extension.log](validation/existing-project-extension.log).
The 14 new tests cover project scan limits, pagination, LFS placeholders, symlink/path
boundaries, separate workspace enforcement before writes, profile separation,
asset hashes, idempotency across restart/catalog changes, interrupted binding creation,
changed sources before/during collection, request ownership and actual CLI stdio wiring.
The MCP-to-material test uses the real service/collector with scripted HTTP responses;
it verifies generation provenance and byte-for-byte preservation of the synthetic
project. It does not run a GPU model or parse the opaque `.uasset` fixture. No existing
game package, rig, UV layout, editor integration or gameplay performance is certified.

The first Windows 3.11 CI attempt exposed a workspace comparison using a noncanonical
path in the overlap regression: `FileNotFoundError` instead of refusal before writes.
Preserved failure: [job 119245228408](https://github.com/swisspatate/loopcut/actions/runs/39606871224/job/119245228408).
The fix resolves both project and workspace paths before comparing containment,
including Windows short-name aliases. The same test now also checks lexical `..`
and the parent workspace; no test was skipped or relaxed. The 239-case log above
precedes this fix; the final targeted **14 tests pass in 2.417s**, including the
expanded path regression. Log: [existing-project-final.log](validation/existing-project-final.log).

Version 0.11 adds the [creative toolkit](creative-toolkit.md). Local regression
discovery reports **225 cases in 163.928s: 224 passed, one socket test skipped** by
the sandbox. All **20 Blender tests** and both compiled C++ tests ran successfully.
After adding the final animated-GLB structural/completeness gate, the **16 creative
tests pass in 6.944s**, including actual Blender generation and inspection. Logs:
[creative-extension.log](validation/creative-extension.log) and
[creative-final.log](validation/creative-final.log).

Coverage includes bounded deterministic recipes, terrain ranges, module dimensions,
RGBA atlases, source material budgets, isolated-worker failure, hashes/relocation,
three saved Blender scenes, PBR after deleting source textures, evaluated liquid/FX,
four IK legs, normalized skin weights, finite animated poses, loop endpoints, in-place
root and six exported GLB actions. Loopcut's binary parser/validator is reused; an
otherwise structural GLB with a missing/renamed clip is rejected. Portable C++ compiles
the exact elemental rules used by the runtime, plus cooldown/energy and particle gates.
Scripted editor tests cover empty-map/destination refusal, owned creations and partial
failure receipts. They do **not** compile Unreal reflected classes or validate UHT,
UMG/Niagara APIs, collision, player behavior, skeletal import or GPU performance.

A standalone generated environment was rendered and visually inspected in stock
Blender Cycles CPU, 960×640, 16 samples, denoising disabled because this build lacks
OpenImageDenoise. This is an inspection image, not a visual-regression baseline or
artistic/performance acceptance. Full-checkout Windows/Linux CI is recorded on the PR.

Version 0.10 adds [agent-facing ComfyUI profiles](comfy-agent-profiles.md). Local
discovery reports **209 tests in 144.462s: 208 passed, one skipped**, including all
**19 real Blender integration tests** and the compiled C++ motion test. The skipped
case exercises real stdio plus loopback HTTP: this sandbox rejects socket creation
with `PermissionError`. It is mandatory in GitHub CI (`CI` prevents that skip).
Log: [comfy-profiles-extension.log](validation/comfy-profiles-extension.log).

The 16 new cases cover profile/template integrity, literal bindings, fixed model/graph
parameters, owned durable IDs, recovery after restart/catalog changes, uncertain POSTs,
interrupted submission, targeted queued deletion, explicit PBR channels, dimension
mismatches, corrupt PNG/receipts, atomic collection and offline verified reuse,
workspace capacity/ownership/path boundaries, opt-in MCP schemas and real CLI/HTTP
transport against a scripted server. Fifteen ran successfully in this sandbox; the
HTTP case and full-checkout Windows/Linux results are recorded separately on the PR.
The example catalog also passes the offline CLI after substituting a measured template
hash in a temporary copy. This does not validate its placeholder checkpoint or execute
a model. Live ComfyUI, GPU results and the user's MCP clients remain local acceptance.

Version 0.9 adds [PBR world previews](world-pbr.md). The local extension suite passes
**193 tests in 138.456s**: 173 pure-Python tests, one compiled C++ motion test and
**19 real Blender integration tests**. The selected **340 upstream regressions**
pass in 5.065s. Logs: [world-pbr-extension.log](validation/world-pbr-extension.log)
and [world-pbr-upstream.log](validation/world-pbr-upstream.log).

The 14 new cases cover complete/duplicate/unknown biome-module assignments, material
sharing, order-independent and relocation-stable appearance identities, changed-map
identity, path/texture/color-space rejection, source-byte and decoded-pixel budgets,
plan-only CLI behavior, snapshot/source races and failed-worker receipts. A real
four-zone build shares two meshes and three materials, including two variants in the
same biome. It checks source hashes, removes the original inputs, relocates the output,
then opens only the `.blend` in an otherwise empty directory. Packed PNG bytes, color
spaces, shader wiring, image decoding, object material overrides, transforms and late
animation subframes are checked. Altered PNG, appearance and blend artifacts are
rejected. A second real Blender case rejects colored roughness without saving a world.

The existing two-zone example also builds successfully: 36 actors, two PBR materials,
98,304 decoded channel pixels and 53,433 source bytes. The shared packed-material
constructor is reused by material copies and previews; the full suite also exercises
existing theme batches, publishing and reimport paths. Packaged Windows Blender,
visual/texel-density acceptance, GPU memory and live ComfyUI still need local checks.
Automatic textured UE import remains blocked; no Unreal material integration is
claimed. Full-checkout and Windows/Python CI results are recorded on the PR separately.

The initial full-checkout CI run exposed a pre-existing timing assertion in
`test_jobs.StatusWaitTests.test_returns_when_the_job_ends`: a real 0.3-second timer
was delayed enough to display `Waited 1s`, while the assertion hardcoded `Waited 0s`.
The test now accepts the rounded 0–3 second display while retaining its measured
`took < 3` bound, complete-state/message checks and exactly two main-thread calls.
Runtime code is unchanged. All **25 job tests pass in 2.902s** locally; see
[world-pbr-job-wait.log](validation/world-pbr-job-wait.log). The final PR head runs
the full CI suite again; the initial failed run is not reported as successful.

Version 0.8 adds [combined Blender world previews and geometry QA](world-preview.md).
The local extension suite passes **179 tests in 143.999s**: 161 pure-Python tests,
one compiled C++ motion test and **17 real Blender integration tests**. The selected
**340 upstream regressions** pass in 5.466s. Logs:
[preview-extension.log](validation/preview-extension.log) and
[preview-upstream.log](validation/preview-upstream.log).

The 15 new tests cover touching faces, static penetration, conservative swept-box
warnings, collision-disabled decoration, malformed connectors, actual socket geometry,
plan tampering, duplicate identities, bounded findings, coordinate conversion, mixed
periods, source snapshots, preflight/no-launch behavior, worker failures, deadlines and
exclusive destinations. A real Blender test builds a three-zone world from two kits
with 80- and 140-frame periods, verifies shared meshes and object material overrides,
then samples subframes through frame 280. Short-period objects keep animating past
their initial two cycles. Source artifacts remain unchanged; altered output artifacts
and a forged source hash fail checks. Portable integrity checks still work after
removing the original kits. This is not an authenticity or provenance signature.

The existing example also produces a two-zone, 36-actor `.blend` with zero geometric
errors/warnings. No Unreal or ComfyUI execution is implied. Packaged Windows Blender,
UE 5.8 plugin/UHT compilation, real collisions, controller traversal and rider transport
remain local acceptance steps. Full-checkout and Windows/Python CI results are recorded
on the milestone's pull request, separately from these local logs.

Version 0.7 adds [world assembly, periodic biome maps and Unreal runtime review](world-runtime.md).
The final local suite passes **164 tests in 126.934s**: 147 pure-Python tests, one
compiled C++17 motion test and 16 real Blender integration tests. The selected
**340 upstream regressions** pass in 5.432s. Logs:
[assembly-extension.log](validation/assembly-extension.log) and
[assembly-upstream.log](validation/assembly-upstream.log).

The 20 new tests cover connector widths/movement compatibility, centre-exit reachability,
seeded off-track decoration, actor budgets, palette/path bounds, periodic texture fields
and analytic derivatives, generated PNG/Material Doctor bundles, relocation-stable world
IDs, and failure to overwrite. Fake Unreal tests exercise empty-map preflight, missing
plugin/version/mesh rejection, material/actor/save failures, partial ownership receipts,
and read-only PIE pose sampling. These are protocol tests, not engine execution.

The engine-free C++ triangle-wave implementation is compiled with g++ using C++17,
`-Wall -Wextra -Werror`, then compared with Python across periods, phases, negative time,
subframes and repeated cycles. The Unreal actor/module itself is **not compiled** here:
no UnrealBuildTool, UHT, editor, collision simulation or real player controller was available.

Real Blender tests build two different module lengths, connect their checked kits, relocate
intact inputs without changing the plan, generate two PBR themes, publish their packed maps,
check source hashes and reject a changed kit artifact. The documented example separately
builds two zones, 36 planned actors, one connector and four successful material variants;
its Unreal dry run remains `planned` and `engine_validated=false`. Windows packaged Blender,
full UE 5.8 plugin compilation, material APIs, runtime poses/collision/rider behavior and
textured imports require the local commands and acceptance steps in the guide.

Version 0.6 adds [layered runner paths, cyclic lifts and theme batches](worlds-and-themes.md).
The final local extension run passes **144 tests: 129 portable and 15 real Blender
tests**, in 98.480s. The selected **340 upstream regressions** pass in 5.094s.
Logs: [worlds-extension.log](validation/worlds-extension.log) and
[worlds-upstream.log](validation/worlds-upstream.log). No native Loopcut source changed.

The 19 new cases cover unequal-height ballistic landings, elevated leading-face
clearance, branch rejoining, exclusion of moving platforms from static certification,
seeded phases, cyclic extrema/subframes, Unreal units, bounded recipe/assignment rules,
snapshot mutation, failed-worker/deadline receipts and refusal to overwrite. Real
Blender tests inspect the animated preview at fractional frames and cycle boundaries,
build/export two assets with two different themes, verify packed image assignments and
preservation of other objects' materials, and reject a missing object without changing
the original scene. The animation test exposed Blender's API key insertion using
Bezier interpolation despite the UI preference; explicit linear F-curve keys now pass.

The example CLI builds 24 placements including 6 moving side platforms. A scan of 128
seeds finds no static-route failures. `dynamics_validated=false` and
`engine_validated=false`: no moving-branch jump, Unreal consumer, collision/controller,
live ComfyUI generation or Windows Blender runtime is claimed validated. See the exact
local acceptance steps in the guide. Full-checkout and Windows/Python matrix CI results
are tracked on this milestone's pull request separately from the local logs.

Version 0.5 adds the [Runner module kit](runner-kit.md). The local extension suite passes
**125 tests: 113 portable and 12 real Blender tests**, in 78.120s. The runner-specific
suite was rerun after bounding text artifact reads: **24 tests passed** in 14.509s,
including two real Blender integration cases. The selected **340 upstream regressions**
pass in 5.016s. No native Loopcut source was changed.

Runner checks cover deterministic seed output across Python versions, numeric/schema
limits, capsule clearance, ballistic launch windows, landing/recovery propagation,
an explicit pairwise-connectivity counterexample, adjacent-lane timing, CSV axis/unit
conversion, SVG structure, seed scans, failed-preflight/no-launch behavior and refusal
to overwrite. Real Blender tests build two module sizes, inspect the preview's shared
mesh placements, reimport the GLB to verify geometry/pivot, and reject corrupted or
oversized artifacts. A CLI demo built the example's 19 placements and a valid module
publication. A 128-seed scan of that recipe returned no model failures. This is not
an Unreal/controller playability result.

Logs: [runner-extension.log](validation/runner-extension.log),
[runner-tests.log](validation/runner-tests.log),
[runner-upstream.log](validation/runner-upstream.log).
The kit's native Unreal/PCGEx setup, collision and actual gameplay still require the
local checks in the guide. Windows/full-checkout CI results are recorded separately
on the Runner kit pull request.

Version 0.4 adds the [PBR/ComfyUI pipeline](material-pipeline.md). The local extension
suite passed **101 tests: 91 portable and 10 real Blender tests**, in 92.160s. This includes
scripted ComfyUI HTTP responses, receipt recovery, queue cancellation, PNG byte/path
validation, material bundles, real packed-texture GLB publication/reimport and six
unsupported shader/UV/image cases. Pixel checks verify the roughness G/metallic B packing
and normal values after reimport. Source hashes remain unchanged. After moving textured
Unreal rejection ahead of the engine import, the affected integration plus publisher
tests were rerun: **21 passed** in 8.488s. The selected upstream set passes **340 tests**.

Logs: [pbr-extension.log](validation/pbr-extension.log),
[pbr-preflight.log](validation/pbr-preflight.log),
[pbr-upstream.log](validation/pbr-upstream.log).
No live ComfyUI server/GPU/model or Unreal editor ran. HTTP tests use a scripted peer
and a mocked urllib response; they do not establish installed server compatibility.
The Unreal textured path only plans and rejects automatic apply before mutation.
Windows and complete-checkout CI results are tracked separately on this milestone's PR.

Version 0.3 adds Asset Publisher. The local extension run passed **73 tests**, including
**66 portable tests and 7 real Blender tests**. The publisher-specific portable tests
were rerun after final receipt/path validation changes. A CLI demonstration created
an asymmetric `.blend`, published it through the queue and generated a standalone
Unreal dry-run plan. The selected **340 upstream regressions** also pass.

Logs: [publisher-extension.log](validation/publisher-extension.log),
[publisher-portable.log](validation/publisher-portable.log),
[publisher-upstream.log](validation/publisher-upstream.log).
Real Blender cases cover source hash preservation, GLB export/roundtrip, copied
rotation/scale and pivot geometry, constant material parameters, quality/guard
rejections, and scripted Codex delegation to the actual Blender publisher. Unreal
tests use an explicit fake editor API; **no Unreal runtime was available**.

The records below describe the earlier v0.2 milestone. Current GitHub matrix/full-suite
results are recorded on the Asset Publisher pull request, separate from local results.

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

No Unreal executable or editor session was available. Version 0.3 implements the
local review importer and runtime probe in `unreal_review.py`. Follow the exact
fixture/PowerShell/editor-console steps in [publisher.md](publisher.md), verify the
installed 5.8 APIs and glTF importer, then check geometry, pivot, axes, units, material
appearance and persistence after reopening the project. Simulated editor tests do
not establish UE compatibility. Rig/skeleton, quadruped animation/root motion and
runner survivability remain separate, unimplemented milestones.

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
