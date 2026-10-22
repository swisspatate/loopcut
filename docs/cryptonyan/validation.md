# Validation record — 2026-10-22

For the consolidated Windows/local acceptance checklist, see
[Checklist des validations sur ton PC](local-pc-checklist.md).
This file retains the cloud test evidence and historical milestone records.

Environment: Linux cloud sandbox, Python 3.12.14, stock Blender 4.3.2 at `/usr/bin/blender`.
Reference upstream: `e07488212ab7f87c77c8b5792785e57620d61ea0`. Source retrieval was
partial through GitHub, not a full clone. This matters for interpreting discovery counts.

## Executed tests

Version 0.24 adds [reference boards](reference-boards.md). The focused suite passes
**23 tests in 7.206s**, including two real Blender Linux 4.3.2 cases; see
[reference-board-targeted.log](validation/reference-board-targeted.log).
One fixture registers actual RNA panels/operators, loads image previews, stores
notes/rectangles, attaches a recipe and prepares a bundle without changing the scene.
The other runs the existing isolated Image Workshop worker and verifies an actual
rendered/exported candidate with unchanged game-source hash. Its reference is a
synthetic PNG and its explicit recipe a box: no artistic reconstruction accuracy
or neural generation is claimed.

Portable cases cover immutable image snapshots, annotation validation, stale revision
and concurrent writer rejection, target drift/LFS/project identity checks, protected
output locations, escaped self-contained HTML, CLI usage, existing connection-profile
compatibility and actual stdio MCP reference/image delivery. No live external AI client
or ComfyUI GPU inference was used. Notes and rectangles remain data for an agent;
the Image Workshop worker does not interpret them itself.

Full extension discovery on the same production code: **515 tests in 232.970s,
512 passed and three sandbox socket skips**; see
[reference-board-extension.log](validation/reference-board-extension.log). The skipped
HTTP preflight/profile/collection cases remain mandatory in CI. The new suite is
included in the existing Windows/Linux Python 3.11/3.13 matrix; its two Blender cases
skip explicitly where the executable is absent. Interactive thumbnails/layout,
HTML rectangle alignment on real references, Claude/Codex vision support and the
existing Unreal project's assets remain in the [PC checklist](local-pc-checklist.md).

Version 0.23 adds [agent connection setup](agent-connections.md), inspired by
Mixar's public MCP setup UX and implemented independently over the existing bridge.
The focused suite passes **19 tests in 3.083s** with no skips; see
[agent-connect-targeted.log](validation/agent-connect-targeted.log). It exercises
actual stdio subprocesses, JSON/TOML configuration roundtrips with Unicode/spaces,
concurrent clients and completed mock audits, optional inventory/texture tool discovery,
catalog validation, timeout/protocol failures, read-only ComfyUI metadata via a scripted
transport and a live locked queue that remains byte-identical during diagnostics.

The real Blender Linux 4.3.2 fixture registers/unregisters actual RNA classes, saves
and reloads the profile, invokes copy operators and runs a real MCP diagnostic.
The final focused run also exercises the asynchronous diagnostic operator by
advancing its timer events explicitly and verifies stale-result rejection after
settings change. Background Blender has no system clipboard/display: interactive
clipboard, rendering of the panel, real UI event-loop behavior and Windows client
integration remain local acceptance work. No model, GPU inference or Unreal ran.

Full local extension discovery: **492 tests in 207.598s, 489 passed and three sandbox
socket skips**; see [agent-connect-extension.log](validation/agent-connect-extension.log).
That run preceded the additional modal-event assertions in the existing Blender
fixture and the Windows lock-test adjustment; the final 19-test focused run above
covers those changes. All production code was
unchanged between the runs. The skipped HTTP/stdio preflight, profile and collection
tests must run in GitHub CI. The matrix now includes the connection suite on Linux
and Windows with Python 3.11/3.13; Blender-only checks skip when Blender is absent.

The initial Windows CI run exposed a test-only portability issue: hashing the live
lock through a second handle is prohibited by Windows mandatory byte-range locking.
The corrected test hashes all queue data and compares lock size/mtime while keeping
the owner lock held. It does not relax queue isolation or change production code.

Version 0.21 adds [reversible material overrides on existing level components](level-material-review.md).
The final focused suite passes **28 tests in 1.177s**; see
[level-material-targeted.log](validation/level-material-targeted.log). It covers read-only
capture, pinned component/actor GUIDs, static and skeletal meshes, exact inherited and
local overrides (including null holes and repeated slot names), deterministic plans,
o-overwrite/offline CLI and escaped HTML comparison, preflight rejection, transactional
write/readback, durable intent before mutation, simulated interruption, conditional
rollback, conflict detection, restoration after a simulated map save and resumable
partial restoration. External actor packages are refused before mutation.

Full local extension discovery: **453 cases in 255.550s, 450 passed and three sandbox
socket skips**; see [level-material-extension.log](validation/level-material-extension.log).
That run began before the final repeated-slot-name compatibility case and explicit
external-actor refusal; the focused suite above covers those final adjustments. Final
extension discovery contains **454 cases**. Existing actual Blender Linux 4.3.2
regressions and engine-free C++ checks pass in the full run; the three HTTP/socket
checks remain mandatory in GitHub CI.

This release changes editor component overrides only on explicit apply. It does not
save maps/assets, modify mesh material defaults, render comparison images or certify
visual quality. Unreal is **not installed here**: transaction notifications, Undo/Redo,
viewport changes, save/reopen persistence and the real project's native Blueprint
components need local acceptance. World Partition/external actor packages, streamed
sublevels and construction-script components require separate adapters. Explicit
asset hashes do not cover the transitive material graph. No private game assets were
used by these fixtures. See the updated [PC checklist](local-pc-checklist.md).

Version 0.20 adds [rich levels and wardrobe](rich-levels-and-wardrobe.md),
[garment fitting](garment-workflow.md) and [reference-aware ComfyUI profiles](comfy-references.md).
Full local extension discovery: **422 cases in 237.566s, 419 passed and three sandbox
socket skips**; see [rich-wardrobe-extension.log](validation/rich-wardrobe-extension.log).
This includes the six garment cases, four running actual Blender 4.3.2: fit/normalized
weights/UV masks/saved-copy readback, deliberately penetrating poses, far garments and
open-body refusal. Original source hashes remain unchanged. The engine-free mechanism
rules compile and execute with C++17 warnings treated as errors.
Final targeted suites pass **16 scene tests in 0.501s** and **seven reference tests in
0.587s**; see [rich-scenes-targeted.log](validation/rich-scenes-targeted.log) and
[comfy-references-targeted.log](validation/comfy-references-targeted.log). Four extra
regression cases were added after full discovery started (ambience, transform readback,
incompatible asset roles and a reference-aware texture collection); these targeted
runs cover them. The final suite therefore contains **426 cases**, including **29 new
cases**. The Windows executable-suffix adjustment was separately rechecked with the
C++ rules test. CLI help and Python compilation also pass with the documented PYTHONPATH.

Coverage includes deterministic density/clearances, modular floors/roof/entrance,
swept lift bounds, source/plan pinning, empty-map/dirty-source guards, rollback,
Skeleton/socket/slot/Leader Pose protocols, fixed LoadImage bindings, PNG hashes,
reference provenance through collection and no duplicate submissions. Legacy profile
contracts remain unchanged when no references are configured. No production game assets
are used. Unreal tests are strict protocol doubles, **not an engine build**; UHT/PIE,
real-character deformations and texture seams, Windows Blender and live ComfyUI GPU
execution remain the [local v0.20 checklist](local-pc-checklist.md). Vertex-distance
checks do not certify continuous cloth collision or visual quality.

Version 0.19 adds [weight corrections on copies](rig-repair.md). The final focused
suite passes **21 tests in 25.755s**, including **five actual Blender 4.3.2 cases**;
see [rig-repair-targeted.log](validation/rig-repair-targeted.log). It covers deterministic
planning, pruning/normalization, auxiliary and locked groups, budgets, source/plan
pinning, no-overwrite CLI behavior, dry-run/failure receipts and malformed plan rejection.
Actual Blender checks save and independently reopen a candidate with UVs and a shape
key, preserve source hashes, retain unweighted vertices for manual work, reject external
resources/shared data and detect deliberately changed geometry after saving.
Full local extension discovery: **396 cases in 221.832s, 393 passed and three sandbox
socket skips**, including 31 actual Blender cases and both engine-free C++ checks;
see [rig-repair-extension.log](validation/rig-repair-extension.log). That run preceded
the final receipt distinction between planned and changed vertices, no-op reporting,
plan-size newline accounting and incomplete-plan guard. The focused suite above covers
those final changes and the extra regression case; the resulting suite has 397 cases.
Blender Windows and the real game character remain unvalidated. Weight/geometry checks
do not certify visual deformation, runtime IK, imported Unreal influences or adoption
into the existing game. No private game assets are used by the fixtures.

Version 0.18 adds [Unreal pose capture and Rig Doctor](rig-and-unreal-animation.md).
Final full local extension discovery: **376 cases in 211.086s, 373 passed and three
sandbox socket skips**; see [rig-unreal-extension.log](validation/rig-unreal-extension.log).
All **25 new cases** pass: 12 Unreal protocol tests and 13 rig tests, including three
actual Blender 4.3.2 cases. The full suite includes 26 actual Blender cases and both
engine-free C++ checks. The three socket tests remain mandatory in GitHub CI.
Coverage includes component/world separation, nonidentity root rotation, axes and
quaternion conversion, endpoint sampling, source/skeleton/sidecar drift, dirty content,
pose/bone/scale guards, influence counts and sums, auxiliary groups, bounded evidence,
hierarchy/budget validation, real CLI no-overwrite behavior and source preservation.
The Blender fixture deliberately contains unweighted vertices, half-normalized weights,
five influences and helper-only assignments. The real worker rejects ambiguous bindings.
Unreal uses strict API doubles, **not an installed engine**. RAW source pose reading,
root-motion options and the 5.8 API still need local acceptance. No actual game rig,
runtime IK/Blueprint, deformation, cooked import, GPU or visual result is certified.

Version 0.17 adds [Creative Director](creative-director.md). The focused suite has
**32 tests passed in 0.902s**; see [director-targeted.log](validation/director-targeted.log).
Coverage includes deterministic frame/layout calculations, source/sidecar and project
pinning, contact re-audit, socket/skeleton/length gates, copy-only effects, notify timing
and parameter readback, named Sequencer channels and camera cuts, architecture placement
and rollback receipts, source changes, dirty content and real offline CLI execution.
The final targeted run also covers frame/tick quantization readback and rejects a
one-frame key shift, including for uncommon integer display rates.
Full local extension discovery: **350 cases in 232.082s, 347 passed and three sandbox
socket skips**, including all 23 existing actual Blender tests and both C++ checks;
see [director-extension.log](validation/director-extension.log). That run preceded
the final frame/tick readback adjustment and its extra regression case; the focused
suite above covers the final code. The resulting extension suite contains 351 cases.
Editor operations use strict protocol doubles, **not Unreal**. No game character,
Niagara rendering, Sequencer playback, packaged build, collision or navigation result
is certified. The PC checklist records the remaining engine acceptance checks.

Version 0.16 adds [Animation Doctor](animation-doctor.md). Final focused suite:
**22 tests passed in 10.976s**, including **three actual Blender 4.3.2 cases**;
see [animation-final.log](validation/animation-final.log). The custom-named fixture
uses two actions, a world-space constraint and centimetre scene units. Assertions
cover evaluated poses, action selection, source hashes, contact speed and rejection
of missing bones/out-of-range sampling. Portable tests cover root-relative seams,
quaternion sign equivalence, nonuniform sampling, declared-contact uncertainty,
thresholds, bounds and real offline CLI output/exit codes.

Full local extension discovery: **319 cases in 295.295s, 316 passed and three
sandbox socket skips**, including 23 actual Blender tests and both C++ checks.
See [animation-extension.log](validation/animation-extension.log). This run started
before the final bounded-JSON-read/large-integer validation adjustment; the focused
suite above validates the final code. Windows/Linux CI checks the published commit.

This does not validate the user's actual rig, Blender Windows, layered action slots,
Unreal animation extraction, retargeting, weights or Niagara/AnimNotify application.
There is no new GPU/model requirement. Local acceptance steps are recorded in the
central checklist; events are unapproved timing candidates only.

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


## v0.22 — Image Workshop

Les tests ciblés vérifient recettes, hashes PNG/GLB, références déclarées,
refus des sources externes et GLB hors contrat, budgets, chemins, CLI, HTML,
reçus d'échec et timeout. Deux tests utilisent réellement Blender 4.3.2 Linux :
primitives/rendu/export/réouverture et import d'un GLB texturé avec vérification
que l'image reste empaquetée dans le `.blend` sauvegardé.

Commande : `python -m unittest discover -s loopcut/tests -p test_cryptonyan_image_workshop.py -v`.
Journal ciblé : [image-workshop-targeted.log](validation/image-workshop-targeted.log).
La suite complète des extensions est dans [image-workshop-extension.log](validation/image-workshop-extension.log).

L'exemple temple a également été exécuté avec Cycles CPU, 512×512, 16 samples :
7 meshes, 532 triangles, aucune boîte englobante hors caméra, Asset Doctor passé.
Le rendu a été inspecté. Sa référence est une image synthétique uniforme de test :
il valide l'exécution de l'exemple, **pas une reconstruction fidèle d'image**.

Aucun workflow TRELLIS/ComfyUI, modèle de vision, GPU Windows ou import Unreal
réel n'a été exécuté ici. Leurs validations figurent dans la checklist PC ; les
sources consultées pour les moteurs sont liées dans l'étude des générateurs.

Résultats locaux : suite ciblée finale **19 tests réussis en 12,970 s** ; suite
complète des extensions **472 tests en 256,768 s, 469 réussis et 3 ignorés**
(sockets interdits par le sandbox, tests obligatoires dans la CI). Après cette
suite complète, le garde-fou des budgets cumulés sommets/textures par instance a
été ajouté et vérifié par la suite ciblée finale ; le total final est **473 tests**.
Les deux vrais parcours Blender ont été rejoués dans cette suite ciblée finale.
