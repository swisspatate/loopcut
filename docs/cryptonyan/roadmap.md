# Next milestones

For checks to perform on the user's PC, use the
[central local validation checklist](local-pc-checklist.md). It distinguishes
implemented features awaiting local acceptance from the development work below.

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
   durable request idempotency and verified Material Doctor collection. Next add installed
   model/node preflight, profile previews, biome variation batches and seam-quality checks.
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

Recommended next Codex task: connect Claude Code to this stdio service on the user's
Windows machine, run the full test commands with the exact Loopcut Blender 5.2.2 binary,
then validate the experimental Codex adapter using an existing local sign-in. A live
multi-specialist Loopcut integration remains separate from this bounded Asset Doctor tool.

For the asset pipeline, validate the asymmetric and PBR fixtures in Unreal 5.8 and a
hash-approved ComfyUI workflow on Windows. Next add the Unreal texture gate and a
verified Material Maker export adapter, followed by PCGEx module kits. See the integration
table in [material-pipeline.md](material-pipeline.md); none of those future projects is installed.
