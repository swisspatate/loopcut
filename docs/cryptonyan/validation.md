# Validation record — 2026-10-22

For the consolidated Windows/local acceptance checklist, see
[Checklist des validations sur ton PC](local-pc-checklist.md).
This file retains the cloud test evidence and historical milestone records.

Environment: Linux cloud sandbox, Python 3.12.14, stock Blender 4.3.2 at `/usr/bin/blender`.
Reference upstream: `e07488212ab7f87c77c8b5792785e57620d61ea0`. Source retrieval was
partial through GitHub, not a full clone. This matters for interpreting discovery counts.

## Executed tests

Version 0.36 adds [agent-selected ComfyUI references](comfy-reference-preparations.md).
The focused suite passes **26 tests in 3.199s: 25 passed, 1 skipped**; see
[reference-preparations-targeted.log](validation/reference-preparations-targeted.log).
Full extension regression passes **793 tests in 355.995s: 789 passed, 4 skipped**;
see [reference-preparations-extension.log](validation/reference-preparations-extension.log).
Python source was frozen throughout this final broad run. The four local socket
restrictions are exercised by mandatory GitHub CI tests, including the new real
stdio → loopback HTTP → prepare/preflight/project submission/collect/review/native
image acceptance test. Its HTTP peer scripts generation; no GPU model runs.

Checks cover closed operator slots, source handle/path/symlink boundaries,
protected game/assets/receipt roots, image and aggregate budgets, content-addressed
no-overwrite staging, all three roles, prepared graph/model preservation, normalized
Windows-compatible input paths, changed sources/staged files/profile, drift during
preparation or the metadata GET, preparation integrity, interrupted preparations,
lost POST response recovery and historical review after reference removal.
Asset-bound requests retain target guards; ordinary/fixed-reference profiles and
their collections remain supported. Dynamic slots are explicitly rejected before
collection planning and currently use individual prepared requests.

The all-configured tools/list response is **60,553 bytes / 52 tools**, below the
262,144-byte probe budget. Texture-only configuration exposes 20 tools; adding the
project exposes 33. Connection profiles and older ComfyUI catalogs remain valid.
Live model conditioning, mask alpha/conversion, UV fidelity, actual Claude/Codex
Windows clients, Blender Windows and Unreal 5.8 rendering/adoption remain local
acceptance tasks in the v0.36 [PC checklist](local-pc-checklist.md).
GitHub CI checks the exact published revision and is linked in the pull request.

Version 0.35 adds [offline ComfyUI texture review](comfy-texture-review.md).
The final focused suite passes **18 tests in 2.475s**; see
[comfy-texture-review-targeted.log](validation/comfy-texture-review-targeted.log).
Full extension regression passes **767 tests in 416.616s: 764 passed, 3 skipped**;
see [comfy-texture-review-extension.log](validation/comfy-texture-review-extension.log).
Python source was frozen throughout this final run. The three socket/stdio cases
remain active in GitHub CI, which validates the exact published revision.
This broad run preceded a test-only Windows correction: the read-only assertion
now inventories owner-lock files without hashing their actively locked bytes,
and still hashes every data file. Windows correctly refused that lock read.
Production code is unchanged; the final focused run above includes the correction.
Two separately collected scripted ComfyUI outputs become real frozen PBR layer
inputs through the returned work: handles and manifest bindings; the existing
Studio queue composes the expected sRGB pixel value 188 without further HTTP calls.
Native MCP PNGs preserve their original bytes. Read-only review preserves the
workspace and game fixtures; asset-bound reads reject changed sources.

Tests cover missing/uncollected/uncertain requests, absent channels, invalid IDs,
file/hash/symlink changes, provenance disagreement after manifest rehash, replaced
material maps, profile removal, wrong Studio roots, source drift, project-binding
mismatches, over-budget image display and changes during the final image read.
The collector and reviewer now share strict request/generation/file-set checks;
Studio and textures share the existing bounded artifact reader. No PNG resampling
or new channel synthesis occurs. All-configured tools/list is **56,917 bytes /
48 tools**, below the 262,144-byte probe budget. Existing profile fields are unchanged.

The real stdio/loopback-HTTP acceptance case now also inspects and displays a
collected texture. The local sandbox restricts sockets, so that case remains
required in GitHub CI. Scripted ComfyUI responses do not validate inference, GPU,
installed nodes/models or their bytes/licenses. No new Blender or Unreal execution
is introduced by this feature. Windows clients, actual GPU workflows and final
UV/slot/render acceptance remain in the v0.35 local PC checklist.

Version 0.34 adds [verified workflow snapshots and explicit prefix reuse](workflow-reuse.md).
The final focused suite passes **23 tests in 24.080s**; see
[workflow-reuse-targeted.log](validation/workflow-reuse-targeted.log).
Full extension regression passes **749 tests in 407.846s: 746 passed, 3 skipped**;
see [workflow-reuse-extension.log](validation/workflow-reuse-extension.log).
The three local socket/stdio restrictions remain exercised by GitHub CI.
Python source was frozen throughout this final full run.
This broad run preceded a test-only deadline correction: Windows CI showed that
50 ms could elapse before the first snapshot was durable. The test now expires
the real worker execution scope after that snapshot is captured, independent of
disk speed. No production code changed; the final focused run above includes the
correction, and CI runs the exact published revision on all platforms.
It exercises a genuine failed PBR chain, removes the original source maps, and
composes the expected linear-color/roughness pixels from the verified snapshot.
A real Blender 4.3.2 rig audit is retained after a deliberately invalid policy;
the fixed retry skips that audit, repairs a new candidate and verifies it after
reopening while the original rig hash stays unchanged. A real stdio client inspects
the failed parent, reads its report, forks and executes a new pinned workflow.

Checks include rejected-result diagnostics, identical-prefix enforcement, changed
criteria, active/interrupted exclusion, real cancellation/deadline transitions,
changed configuration, added/changed/symlinked files, receipt pin changes, queue-delay
revalidation, ancestor checks during successful replay, eight-link provenance,
deleted history, cumulative snapshot budgets, legacy receipts and native MCP PNGs.
An offline Unreal handoff is regenerated with its new destination; Unreal does not run.
The all-configured tools/list response is **54,670 bytes / 44 tools**, below the
262,144-byte probe limit. The basic Studio launcher exposes 18 tools; profiles are unchanged.
The [Windows update guide](updating-windows.md) documents clean fast-forward updates,
MCP reconnection and preservation of profiles/history without a complete reinstall.

Windows Blender, actual Claude/Codex applications/model choices, ComfyUI inference
and Unreal 5.8 remain local acceptance tasks; see the v0.34 PC checklist.
Reused outputs carry source_freshness_validated=false: no current-source audit is claimed.
GitHub CI checks the exact final revision and is linked in the pull request.

Version 0.33 adds [sequential Studio workflows](studio-workflows.md).
The final focused suite passes **29 tests in 21.178s**; see
[studio-workflows-targeted.log](validation/studio-workflows-targeted.log).
Full extension regression passes **724 tests in 361.523s, 721 passed, 3 skipped**;
see [studio-workflows-extension.log](validation/studio-workflows-extension.log).
The three local socket/stdio restrictions remain covered in CI. This full run
preceded the final early-terminal-state adjustment and two additional cases;
the final focused suite above includes both early cancellation/configuration failure
and the Image Workshop chain. GitHub CI checks the exact published final revision.

All five templates are exercised with actual module execution: frozen PBR maps
are composed into expected color/roughness pixels without altering their sources;
Blender 4.3.2 creates a camera preview, imports actual modular GLB files, performs
an audit/plan/repair-copy sequence with a separate saved-candidate verification,
and renders/exports an explicit Image Workshop recipe. The rig source and image
reference retain their hashes. This uses fixtures, not the user's actual character
or levels. The image case is recipe-driven construction, not neural image-to-3D.

CPU tests also prepare a comparison plan and an inert Unreal handoff with the
configured project; no engine is imported or executed. A real exported-launcher
stdio client builds a template, submits the whole material workflow, polls its
receipt, repeats its stable ID and reads the verified workflow journal. The
existing routing suite passes **26 tests in 5.212s**; see
[studio-workflows-routing.log](validation/studio-workflows-routing.log).
Catalog coverage now includes 30 public families, 19 execution operations (18
primitives plus workflow_run), the new CLI and conditional template tool.
The all-configured tool-list response is 51,413 bytes, below the connection probe's
262,144-byte response budget. Existing profile fields remain unchanged.

Tests cover ordered dependency validation, duplicate/unsafe/Windows-reserved step
IDs, nested-workflow rejection, closed/bounded schemas, literal recipe text,
result-field and array-index checks, boolean/number distinction, missing fields,
rejected results, failed or cancelled steps blocking their successors, shared
execution budget, frozen retries after source removal, late configuration checks,
producer hash/file-set/receipt changes, directory/file bindings and path lists,
final input verification, durable progress and interrupted parent/step journals.
A controlled worker-start gate exercises cancellation after the future starts but
before the first step, plus configuration failure before dispatch: unstarted
steps become blocked and no step output is created. No retry/resume is introduced.

A first local broad run overlapped the final schema edit: its already-imported
probe expected the older schema while its new subprocess loaded the changed one.
That catalog mismatch was isolated and the broad suite rerun with source frozen;
the passing 724-test log above is that rerun. The isolated reference/profile probe
also passes **1 test in 0.347s**; see
[studio-workflows-probe.log](validation/studio-workflows-probe.log).

No real Claude/Codex model or client application, Windows Blender, ComfyUI inference
or Unreal editor was exercised in this cloud run. Studio workflows do not submit
ComfyUI network calls; collected maps can feed their material template. CPU
cancellation is cooperative, the 600s budget covers the whole workflow, and a hard
crash may leave Blender children requiring local inspection. The queue remains
per workspace, with no global GPU arbitration. Local acceptance is tracked in the
[central PC checklist](local-pc-checklist.md).

Version 0.32 adds [background Studio operations](background-operations.md).
The final focused suite passes **21 tests in 6.467s**; see
[background-operations-targeted.log](validation/background-operations-targeted.log).
Full extension regression: **695 tests in 293.144s, 692 passed, 3 skipped**;
see [background-operations-extension.log](validation/background-operations-extension.log).
The same three local socket/stdio cases remain enabled in CI. The full run preceded
the final receipt locking refinements and two additional concurrency regressions;
the focused suite above ran after those fixes. GitHub CI checks the published final source.

The tests exercise immediate MCP submission while a controlled operation is busy,
queued/running/indexing cancellation, shared IDs across asynchronous/synchronous APIs,
concurrent duplicate requests, frozen arguments, queue saturation, deadline recovery,
late path/configuration checks, durable errors, recent history and owner lock retention
during graceful shutdown. Restart fixtures cover all three unfinished states and
prove that no work is resumed. They simulate persisted crash state; they do not
prove automatic cleanup after a hard server crash.

A real exported launcher is driven through stdin/stdout to submit, poll, list,
cancel a terminal request and read a verified camera artifact. A real Python child
spawns a descendant with a heartbeat; cancellation stops the process tree and its
writes. Two actual Blender 4.3.2 tests run a normal camera preview and cancel a
long fixture after it saves a partial .blend. The latter substitutes only the
camera workload script to keep Blender active until cancellation. The actual
Blender process exits; the retained copy has no completed artifact manifest.

The first published CI head passed both Linux matrix jobs and the global suite,
but [Windows 3.13 failed two asynchronous success cases](https://github.com/swisspatate/loopcut/actions/runs/39778865330/job/119824681970)
while polling operation receipts; fail-fast cancelled the sibling Windows 3.11 job.
Receipt readers now share the publication lock, preventing Windows file-replacement
conflicts with open read handles. A controlled open-reader regression verifies that
publication waits. A second regression gates cancellation publication while a
synchronous waiter wakes: execute now waits for the committed terminal receipt.
That test also reproduced the old failure when the previous unlocked execute method
was injected locally. These cases pass in the final focused suite above; final CI
runs are linked in the PR.

Cancellation propagates through a thread-local ContextVar scope into existing
ExecutionContext/run_process polling. This reuses the existing process-tree cleanup,
isolated environment and worker deadlines without changing eight Blender APIs.
CPU operations remain cooperative at boundaries; the 600s Studio budget is not a
hard CPU preemption guarantee. Every restarted unfinished receipt is interrupted;
after a hard crash, old Blender processes still require inspection before retrying.

No external Claude/Codex model, Windows Blender, ComfyUI inference or Unreal editor
was executed locally in this cloud run. Client behavior, Windows Blender process
cleanup and real project/GPU integration remain in the
[central PC checklist](local-pc-checklist.md). Portable CI also tests real Python
process cancellation and descendants on Windows; no Blender executable is installed
by that workflow. The Studio queue is per workspace and is not a global GPU arbiter.

Version 0.31 adds [agent capability discovery/routing](agent-routing.md).
The focused suite passes **26 tests in 3.995s**; see
[agent-routing-targeted.log](validation/agent-routing-targeted.log).
A labelled set of **26 FR/EN prompts** also matches the expected advisory routes.
This evaluates the bounded lexical shortlist, not a language model or an external
Claude/Codex client's decisions. No model, sign-in or paid API was called.

Catalog tests check all 29 public workflow families, documentation paths, coverage
of every public CLI entry point (excluding private workers), and all 18 allowlisted
execution operations. Configuration and actual connected tools determine readiness.
The tests cover negated generation requests, unknown/ambiguous goals and inert prompt
text; these are not a general semantic or prompt-injection robustness guarantee.

A real exported-launcher stdio client initializes the server, receives instructions,
routes a goal, prepares a camera program and reads its verified artifact/receipt.
Native workflow prompts, image content blocks, guidance exports, strict operation
arguments, approved handles, source/sidecar snapshots, cached retries, configuration
identity, changed artifacts, interrupted recovery and owner locks are also exercised.
CPU cases prepare actual modular GLB bundles and an inert Unreal handoff script;
no editor is imported or run. A real Blender 4.3.2 case invokes wardrobe review via
MCP, verifies the saved copy, source hash, unchanged weights and sampled findings.

Full extension regression: **676 tests in 272.554s, 673 passed, 3 skipped**.
See [agent-routing-extension.log](validation/agent-routing-extension.log).
The same three HTTP/stdio tests are skipped by local socket restrictions and remain
active in CI. The final guide/configuration metadata is also verified by the
focused suite above. Existing connection probes still use disposable workspaces;
the real operation journal is not opened during diagnostics.

The first Windows 3.11 CI run exposed an implicit-encoding bug in the routing
fixture reader: UTF-8 French accents were decoded using the Windows default code
page, causing three labelled routes to differ. The fixture/source readers now
select UTF-8 explicitly. The real MCP server also configures stdin/stdout as strict
UTF-8, independently of the host locale. The real-stdio test forces CP1252 before
startup and sends an unescaped UTF-8 French prompt, then checks the correct route.

After that correction, the focused suite passes **26 tests in 3.995s**, and the
connection and bridge suites pass **19 tests in 4.082s** and **35 tests in 1.931s**.
See [connection UTF-8 regression](validation/agent-routing-connection-utf8.log) and
[bridge UTF-8 regression](validation/agent-routing-bridge-utf8.log). The full local
676-test run above preceded this final encoding correction; final CI runs on the
corrected commit are linked in the PR.

Actual Claude/Codex choice and instruction handling, Windows file/timeout behavior,
ComfyUI inference and Unreal handoff execution remain on the local checklist.
Operation success is not artistic or engine certification. The new MCP execution
is synchronous, has no independent cancellation queue and never resumes interrupted
calls automatically. CLI-only workflows and unfinished TRELLIS mesh collection are
explicitly labelled; no live editor RPC or general 3D reconstruction is implied.

Version 0.30 adds [a common Unreal comparison stage](unreal-comparison.md).
The focused suite passes **22 portable tests in 0.821s**; see
[unreal-comparison-targeted.log](validation/unreal-comparison-targeted.log).
All editor cases use strict API doubles extending the existing material inspector
double. No real Unreal, renderer, camera viewport, evaluated skeletal pose or GPU
benchmark was executed. The Epic 5.8 Actor/SkeletalMeshComponent API documentation
and single-node data index were consulted; documentation is not runtime evidence.

The tests exercise deterministic plans tied to saved maps, source packages,
sidecars and project descriptors; actual CLI preparation; shared positions,
component-only material overrides and unchanged original package hashes; camera
look-at, light and manual exposure settings; requested reference/paused single-node
animation data; Skeleton/duration checks; drift rejection for live materials,
camera/light/component transforms and actors; ownership and one-visible-variant
checks; partial placement rollback and interrupted-selection restoration.
A Name-array double deliberately differs from Python list equality and camera
properties round to single precision, to exercise the editor boundary conversions.

PNG collection copies validated bytes and marks provenance as
`user_supplied_png_not_renderer_verified`. Tests run the collection/gallery path,
verify baseline membership, escaped labels, hash rejection and session/conditions
binding. These checks do not authenticate image origin or screenshot timing.

Full extension regression: **650 tests in 268.713s, 647 passed, 3 skipped**.
See [unreal-comparison-extension.log](validation/unreal-comparison-extension.log).
The existing Blender cases still run on Linux Blender 4.3.2. The same three local
socket/stdio cases are skipped by the sandbox and remain active in CI. The last
component-transform/Name-array refinements also pass the focused suite above.

Windows Unreal 5.8 APIs, actual camera framing and exposure, evaluated bones/morphs,
LOD, hidden-instance lighting, streaming/temporal convergence and supplied captures
remain on the local checklist. Automatic renderer capture, GPU measurements,
controlled adoption, BP/Chaos equivalence and clothing assembly are future work.

Version 0.29 adds [animated wardrobe review](animated-wardrobe.md). The focused
suite passes **17 tests in 24.085s**; see
[animated-wardrobe-targeted.log](validation/animated-wardrobe-targeted.log).
Six cases run real Blender 4.3.2. They cover two already skinned garments over two
actions, action-state reset between clips, a non-default unit scale converted to
metres, an actual CLI exit with findings and paths containing spaces, a surface
crossing with no garment vertex inside, and rejection of open bodies, wrong rig
bindings and missing actions. The sidebar fixture registers/unregisters twice,
checks that the source and open scene remain unchanged, and reopens every review
copy to verify action, worst frame, selected garment, markers, shape keys, base
geometry, skin weights and packed resources.

The 11 portable cases cover strict schemas and selection limits, total sampling
budgets/endpoints, distinct mappings, independent parsed values, new output
boundaries, failure receipts, escaped offline HTML/CSV and CLI availability without
Blender imports. The existing garment fitting and rig repair resource guards now
exclude packed resources from external dependency rejection (`packed=False`).
Their real Blender fixtures contain a packed texture; the existing rig repair
unpacked-resource rejection remains active.

Final full extension discovery: **628 tests in 280.402s, 625 passed, 3 skipped**.
See [animated-wardrobe-extension.log](validation/animated-wardrobe-extension.log).
The three existing HTTP/stdio cases remain skipped locally because socket access
is forbidden; Windows/Linux CI keeps them active. This run also covers packed
textures through the existing garment fit and rig repair workers after the fix.

These are sampled nearest-triangle distance signs and bidirectional edge rays,
not continuous collision or cloth certification. No garment/garment assessment,
automatic weight changes, Unreal import/adoption or real-game asset review occurs.
Windows display, the user's character/actions/shape keys and Unreal 5.8 deformation,
LOD and Chaos Cloth remain on the central local checklist.

Version 0.28 adds [constrained modular levels](modular-levels.md). The focused suite
passes **23 tests in 11.198s**; see
[modular-levels-targeted.log](validation/modular-levels-targeted.log).
Two real Blender 4.3.2 cases cover actual GLB instances and a generated room kit.
The first registers the sidebar twice, prepares/checks/builds in an isolated child,
verifies the original open scene and reopens the saved preview to inspect positions,
yaw, shared mesh data and IDs. The second generates five actual floor/wall/door GLBs
with authored proxies through existing Loopcut geometry/export helpers, then builds
and verifies the complete modular preview.

Portable cases check seeded determinism, blockers, disconnected grids, unavoidable
checkpoints even with loops, connector kind/width/height limits, overhead clearance,
tags, actual binary POSITION bounds versus accessor declarations, footprint limits,
hash/tampering rejection, snapshots independent of deleted source files, CSV/Director
unit conversion, output boundaries, bounded search, failure receipts and CLI usage.
The existing Unreal architecture adapter and new mapped-bounds gate use strict editor
API doubles: positive placement, no-spawn dry run and rejection before spawning on
bounds mismatch. No real Unreal installation or game controller was executed.

Final full extension discovery: **611 tests in 247.978s, 608 passed, 3 skipped**.
See [modular-levels-extension.log](validation/modular-levels-extension.log).
The same three HTTP/stdio tests remain skipped locally because socket access is
forbidden; they remain active in Windows/Linux CI. Footprint/proxy graph checks are
not a NavMesh, controller simulation or proof that declared door apertures match
real mesh collision. Native PCG/HISM, terrain placement and vertical ports remain
separate work. Windows display, the user's modules and Unreal 5.8 acceptance are
listed in the central checklist.


Version 0.27 adds [selection context](scene-selection.md) and [mask painting](mask-paint.md).
The focused suites pass **13 selection tests in 2.393s** and **13 mask tests in 0.564s**.
Logs: [scene-context-targeted.log](validation/scene-context-targeted.log),
[mask-paint-targeted.log](validation/mask-paint-targeted.log).

The real Blender 4.3.2 fixture creates a rigged mesh, packed texture and animation,
exports the actual selection through the sidebar, checks UV/material/bone/channel
metadata, builds an editor from a board reference and imports a replayed mask.
It verifies object transforms/data pointers and shader node counts remain unchanged.
Repeated extension register/unregister also succeeds. This fixture runs without a
GUI: the GPU viewport capture is explicitly unavailable in background Blender.
Reuse of Loopcut's capture function is tested separately with a tool double; the
actual graphical capture remains a Windows/local acceptance item.

The mask tests execute the shipped JavaScript under Node: real pointer, undo/redo,
download and wrong-reference import handlers run against small DOM/canvas doubles.
Sixteen seeded multi-stroke projects produce identical JavaScript/Python pixel
arrays. This is not a graphical browser rendering or stylus test. Other cases cover
bound reference snapshots, grey/erase brush behavior, tampering, bounds, interrupted
writes, CLI usage and a painted mask through the actual PBR layer compositor.

Read-only MCP access is tested for both snapshots and masks, including image blocks
and an actual exported-launcher stdio subprocess. No external Claude/Codex client,
ComfyUI GPU inference or Unreal editor was launched. ComfyUI integration reuses the
existing LoadImage bindings; converting opaque RGB mask IMAGE into MASK is a
workflow responsibility documented in the new guide.

Final full extension discovery: **588 tests in 227.072s, 585 passed, 3 skipped**.
See [context-masks-extension.log](validation/context-masks-extension.log).
The same three HTTP/stdio cases are skipped because local sockets are forbidden;
they remain enabled in Windows/Linux CI. All six accepted workstreams and their
remaining steps are tracked in [game-improvement-workshop.md](game-improvement-workshop.md).


Version 0.26 adds [material layers](material-layers.md) and
[camera moves](camera-moves.md). Focused suites pass **18 tests in 2.691s** and
**11 tests in 3.163s**, respectively. Logs:
[material-layers-targeted.log](validation/material-layers-targeted.log),
[camera-moves-targeted.log](validation/camera-moves-targeted.log).

Each suite includes actual Blender 4.3.2 operators with repeated registration and
unregistration. The material fixture composes a PBR bundle, creates a packed
Principled material, validates it with the existing Blender Material Doctor and
exports/validates a real GLB. Raster tests independently exercise all five PNG
filters in RGB/RGBA, linear-space colour mixing, scalar masks, normal mixing,
ordered layers, preserved untouched channels, frozen input independence, bounds,
tampering and CLI usage. Synthetic 2x2 maps prove data flow and numeric behavior,
not production UV seams or appearance quality.

The camera fixture invokes the sidebar and isolated worker, reopens the saved
camera scene, checks cut markers/frame ranges and independently compares actual
camera forward vectors to their targets at every sampled key. Portable tests cover
line/crane/truck paths, orbit radius/heights/two-turn angle continuity, easing,
coordinate units, sampling/singularity limits, tampering, worker-failure receipts,
CLI use and the existing Unreal Director adapter with strict API doubles.

Final full extension discovery: **562 tests in 214.665s, 559 passed, 3 skipped**.
See [creative-authoring-extension.log](validation/creative-authoring-extension.log).
The same three pre-existing HTTP/stdio tests are blocked by local socket policy;
they remain active in CI. No actual Ucupaint installation, ComfyUI GPU generation,
Windows desktop or Unreal 5.8 runtime was used. Ucupaint README/COPYING were read
at pinned revision `3b280e8a874023e4f882be52fbf2d46a32ac6402`; integration is through
exported maps, with no third-party code copied. Camera optics differ between the
Blender preview and Unreal actor defaults and must be reviewed locally.


Version 0.25 adds [visual candidate versions](visual-versions.md). The focused suite
passes **18 tests in 5.270s**, including a real Blender 4.3.2 build followed by
actual RNA/operator archive, compare, select and restore calls. Registration and
unregistration are each called twice, preserving the extension's existing contract.
See [visual-versions-targeted.log](validation/visual-versions-targeted.log).

Portable tests cover source deletion after snapshot, artifact/input tampering,
snapshot identity changes, stale edits, writer exclusion, incomplete attempts,
storage limits, traversal/symlinks, existing/protected destinations, failed copies,
unpublished orphan directories, board provenance/target drift, escaped comparisons
and subprocess CLI use. The real worker fixture uses a synthetic PNG and a box;
it proves file flow and scene preservation, not reconstruction quality. Archives
verify the blend file hash without executing its contents.

The first full run caught duplicate Blender panel registration. The new panel now
uses the same idempotent registration guards as the existing panels; the final
full-suite results below are from the corrected production code.

Final full extension discovery: **533 tests in 222.515s, 530 passed, 3 skipped**.
See [visual-versions-extension.log](validation/visual-versions-extension.log).
The three skips are the pre-existing HTTP/stdio integration cases blocked by local
socket permissions; they remain enabled in GitHub's Windows/Linux jobs. No real
Windows desktop, external model, ComfyUI GPU generation or Unreal 5.8 was used.



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
