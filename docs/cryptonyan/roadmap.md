# Next milestones

Version 0.28 adds [constrained modular levels](modular-levels.md): seeded room graphs,
mandatory checkpoints, branches/loops, typed doors, authored clearance proxies,
verified GLB snapshots, a generated demo kit and actual Blender mesh previews.
CSV/Director recipes reuse the existing engine path; an Unreal-local bounds gate
checks mapped StaticMeshes before delegating to the architecture adapter.


Version 0.27 adds [selection context snapshots](scene-selection.md) and
[offline image-space mask painting](mask-paint.md), exposed through optional Blender
panels and read-only MCP reference tools. Existing Loopcut summaries/capture,
PBR layers and ComfyUI image bindings are reused. The
[existing-game workshop tracker](game-improvement-workshop.md) records all six
accepted areas and their next implementation/local qualification steps.


Version 0.26 adds [masked material layers](material-layers.md) and
[reusable camera moves](camera-moves.md): portable PBR composition from Ucupaint,
ComfyUI or authored maps; sampled dolly/truck/crane/orbit shots for existing Director
recipes and isolated Blender previews. Optional sidebars reuse the same CLI functions.
Ucupaint exchange is through exported maps; native Ucupaint nodes are not imported.


Version 0.25 adds [visual candidate versions](visual-versions.md): verified Image
Workshop archives, optional board provenance, render/recipe comparison, explicit
selection and restoration to a new directory through CLI or Blender sidebar.
It does not replace game assets or restore arbitrary Blender scenes.


For checks to perform on the user's PC, use the
[central local validation checklist](local-pc-checklist.md). It distinguishes
implemented features awaiting local acceptance from the development work below.

Version 0.24 adds [reference boards](reference-boards.md): pinned PNG snapshots,
notes/normalized rectangles, existing-asset fingerprints, an optional Blender sidebar,
self-contained HTML and read-only MCP image access. Explicit recipes prepare existing
Image Workshop bundles. Next: mouse-drawn annotations/free canvas and the user's
actual TRELLIS workflow adapter. Candidate versions are available in v0.25. No autonomous reconstruction.

Version 0.23 adds [agent connection setup](agent-connections.md): optional Blender
sidebar, standalone launcher, Claude/Codex configuration fragments and isolated
MCP/read-only ComfyUI diagnostics. No client sign-in or live viewport control is
implied. [Mixar integration tracking](mixar-integration.md) records the remaining
moodboard, versions, layered materials, TRELLIS and camera work with source/license context.

Version 0.16 adds [Animation Doctor](animation-doctor.md): actual isolated Blender
sampling of mapped existing rigs/actions, root-relative pose seams, motion outliers,
declared world-contact measurements and unapproved event candidates. Versions 0.17–0.19
below extend sampling, skin-weight inspection and editor choreography. World trajectories,
deformation audits and general rig reconstruction remain separate work.

Version 0.17 implements the first [Creative Director](creative-director.md) editor
adapters: Niagara notifies on animation copies, camera-only Sequencer assets and
existing-mesh rows in explicit empty review maps. These have portable protocol tests,
not engine validation. Next qualify them in Unreal 5.8, then add surface-aware effects,
runtime notify deduplication, cinematic triggers/skip/control restoration, Movie Render
Queue and PCG/HISM architecture. No production gameplay assets are replaced here.

Version 0.18 implements [Unreal pose capture and Rig Doctor](rig-and-unreal-animation.md).
RAW AnimSequence component-space traces reuse Animation Doctor; the reader still needs
Unreal 5.8 acceptance. Existing Blender rigs gain bounded base-weight audits with actual
Blender tests. Next: actor trajectories/PIE sampling, retargeted and additive evaluation,
deformation/shape-key metrics and influence-budget comparison after Unreal import.

Version 0.19 implements [reviewed weight corrections on copies](rig-repair.md): pinned
plans, bounded influence reduction and normalization, preservation of locked/auxiliary
groups, saved-candidate reopening and geometry/weight verification. Unweighted vertices
remain manual; no automatic bone assignment, rig reconstruction or Unreal adoption.
Next: visual deformation comparisons, reviewed transfer/interpolation of missing weights,
surface-aware weighting and import/readback of candidate skin weights in Unreal.

Version 0.20 implements [rich scene recipes and wardrobe previews](rich-levels-and-wardrobe.md),
[bounded garment fit/weight transfer](garment-workflow.md), and [reference-aware ComfyUI profiles](comfy-references.md).
Existing assets remain the inputs. Solo mechanisms, lifts, themes, socket accessories,
Leader Pose clothing and sampled vertex penetration checks are implemented prototypes.
Next: qualify Unreal UHT/PIE, real-character fit/UV seams and live GPU workflows;
then surface-aware scatter/PCG-HISM, connected stair/navigation design, continuous
cloth collision, garment authoring, player wardrobe UI/inventory and networking.
No runtime acceptance, automated artistic QA or arbitrary garment synthesis is claimed.

Version 0.21 implements [reversible level material review](level-material-review.md):
selected-component capture, exact inherited/override states, explicit MIC assignment
plans, offline HTML comparison, durable intent before edits and conditional restoration.
GUID/mesh/slot/material conflicts block mutation. No automatic map save or visual score.
Next qualify editor notifications, Undo/Redo, saved/reopened levels, Blueprint/native
components, then matched camera/render captures. External actor packages/World
Partition and construction-script components require separate adapters.

1. **External Claude Code MCP client validation.** Use the provided stdio config with
   the mock executor, then the real Blender executable on Windows. Exercise submit,
   query, cancel and revise in one session. Verify protocol version negotiation against
   the installed client; adopt the official MCP SDK when dependency packaging is agreed.
2. **Real Codex/Loopcut worker dispatch.** The v0.2 `CodexAppServerExecutor` implements
   the local protocol and immutable Asset Doctor tool. Validate an authenticated
   turn locally, then extend it to the native Loopcut integration seam.
   Preserve approval and checkpoint semantics. Deliberately add only mission dynamic
   tools; upstream disables arbitrary configured MCP servers. Keep `CODEX_SPEC` and
   `ORCH_SPEC` distinct. Connect specialist roles through existing worker ownership and
   review/merge machinery. Add crash-safe supervision and Windows Job Objects first.
3. **Extend the ComfyUI adapter.** Version 0.4 implements loopback HTTP submit/status,
   queued deletion, PNG collection and durable receipts; see [material-pipeline.md](material-pipeline.md).
   Version 0.10 adds [configured agent profiles](comfy-agent-profiles.md), six MCP tools,
   durable request idempotency and verified Material Doctor collection. Version 0.14
   adds [read-only metadata preflight](comfy-preflight.md) for nodes, model choices,
   inputs and graph links. Version 0.15 adds [asset-bound texture collections](texture-collections.md)
   with shared style/profile, deterministic seeds, per-item preflight and durable
   recovery. Version 0.20 adds explicitly bound reference/UV/mask images with
   local input staging and hashes checked before submission. Next add profile previews
   and visual consistency/seam-quality checks; shared prompts do not certify artistic consistency.
   GPU execution is not cloud-validated. Pin existing TRELLIS/Pixal3D/multiview workflow hashes and versions;
   allowlist nodes, submit/poll/cancel, stage outputs under the job root. Record model
   hashes, model/output licenses, attribution, seed and generation parameters. Unknown
   license provenance must block distribution. No model/workflow license is assumed.
4. **Validate and extend Asset Publisher.** Version 0.3 implements static mesh GLB
   publication and local Unreal review import with dry-run plans and numerical gates.
   Validate it in the installed 5.8 editor first, following [publisher.md](publisher.md).
   Version 0.4 adds packed PNG PBR publication; automatic textured Unreal import still
   requires measurable material/texture validation. Then add baking, generated collision and LODs, snapshots for
   visual comparison, and incremental rebuilds. Never overwrite existing project assets.
5. **Runner/PCGEx and cat animation.** Implement three lanes, upper/lower branches,
   jumps, portals, moving platforms and three-way choices from seeded graphs. Validate
   actual movement envelopes, collision/capsule sizes, landing windows and platform
   timing in-editor. Quadruped paws/spine/tail/root motion need their own rig tests;
   humanoid retargeting is not true cat support.
   Version 0.5 implements the bounded [flat runner kit](runner-kit.md), including three
   static lanes, jump/recovery window checks, seed scans, Blender generation and a neutral
   point CSV. Native PCGEx mapping, moving platforms and actual gameplay remain unvalidated.
   Version 0.6 adds [upper/lower side paths and cyclic lifts](worlds-and-themes.md),
   actual Blender animation and an Unreal motion contract. Static route checks exclude
   moving branches; a real Unreal motion component and controller tests are next.
   Asset/theme batch publication now reuses the PBR pipeline with explicit assignments.
   Version 0.7 implements [forward kit connectors, biome palettes, periodic maps and
   Unreal review placement](world-runtime.md). The new runtime plugin and PIE sampler
   require local UE 5.8 build/playtests before extending to turns, objective graphs,
   networked motion, phase-switch mechanics or echo-cat gameplay.
   Version 0.8 adds a [combined Blender world preview and geometry report](world-preview.md),
   including shared module meshes, per-instance palettes, mixed-period animation,
   overlap diagnostics and actual socket bounds. These do not replace controller playtests.
   Version 0.9 adds [per-biome/module PBR preview bindings](world-pbr.md), reusing
   Material Doctor bundles, generated maps and embedded Blender image data. A verified
   Unreal texture/material gate remains necessary before enabling textured imports.
6. **Visual/performance regressions.** Wrap existing `inspection.py` / durable render
   jobs for reproducible before/after views, scene hashes, cameras, frames, lighting,
   color settings and seeds. Record GPU/CPU timing and memory on the RTX 5080. Compare
   measurements and captures; aesthetic acceptance remains an explicit human judgment.

Version 0.11 implements the [creative prototype toolkit](creative-toolkit.md): modular
buildings, terrain, animated liquids/FX/weather, a generated quadruped IK rig and six
clips. The runtime now includes elemental powers, reactive surfaces, weather and UMG.
Compile/playtest those components locally before extending them. Arbitrary cat auto-rig,
Control Rig/retargeting, root motion, certified building navigation, physical fluids,
caves, authored Niagara graphs, inventory/progression and networking remain development.

Version 0.12 adds [existing-project discovery and asset-bound texture candidates](existing-project.md).
The current product goal is improving the existing game: reuse its character, rig,
animation, level logic, editor tooling and ComfyUI workflows. Generic creative kits
remain optional demonstrations. Next implement editor-backed dependency/slot inventory
and reviewed material variants using the game's existing import adapters. A generated
PNG is not automatically UV-compatible; no source dependency or rig inspection is implied.

Version 0.13 implements [editor inspection and material variants](unreal-material-variants.md):
direct registry dependencies, mesh slots, parent parameters, skeleton references,
asset-bound plans and isolated MIC/texture/preview-mesh creation. Validate the actual
UE 5.8.3 APIs, shader samplers and save/reload behavior locally. Version 0.21 implements reversible
assignment to selected level components. Matched before/after render capture remains future work; material
layers, VT/ORM and transitive dependency analysis need their own adapters.

Recommended local validation: connect Claude Code to this stdio service on the user's
Windows machine, run the full test commands with the exact Loopcut Blender 5.2.2 binary,
then validate the experimental Codex adapter using an existing local sign-in. A live
multi-specialist Loopcut integration remains separate from this bounded Asset Doctor tool.

For the asset pipeline, validate the asymmetric and PBR fixtures in Unreal 5.8 and a
hash-approved ComfyUI workflow on Windows. Next add the Unreal texture gate and a
verified Material Maker export adapter, followed by PCGEx module kits. See the integration
table in [material-pipeline.md](material-pipeline.md); none of those future projects is installed.


## v0.22 — Référence image et candidats Blender

Implémenté : recette par agent, bundle PNG/GLB haché, primitives ou source statique,
worker isolé, audit Asset Doctor, rendu CPU, export GLB contrôlé et comparatif HTML.
Voir [Image Workshop](image-workshop.md). Pas de modèle de vision embarqué.

Priorité suivante confirmée : intégrer les **workflows TRELLIS déjà présents chez
l'utilisateur** via profils ComfyUI, suivi durable et collecte GLB. Les autres
[générateurs étudiés](image-to-3d-providers.md) restent optionnels. Validation visuelle,
Windows/RTX/Unreal et adoption dans le vrai jeu restent locales.
