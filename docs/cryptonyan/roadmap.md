# Next milestones

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
3. **ComfyUI adapter.** Pin existing TRELLIS/Pixal3D/multiview workflow hashes and versions;
   allowlist nodes, submit/poll/cancel, stage outputs under the job root. Record model
   hashes, model/output licenses, attribution, seed and generation parameters. Unknown
   license provenance must block distribution. No model/workflow license is assumed.
4. **Unreal 5.8 MCP/import bridge.** Validate the installed editor/plugin API versions.
   Start with dry-run import plans into a new review folder; validate names, units/axes,
   materials, LODs, collision meshes and sockets. Reuse Loopcut GLB validation and compare
   imported bounds/triangle counts. Never overwrite existing project assets automatically.
5. **Runner/PCGEx and cat animation.** Implement three lanes, upper/lower branches,
   jumps, portals, moving platforms and three-way choices from seeded graphs. Validate
   actual movement envelopes, collision/capsule sizes, landing windows and platform
   timing in-editor. Quadruped paws/spine/tail/root motion need their own rig tests;
   humanoid retargeting is not true cat support.
6. **Visual/performance regressions.** Wrap existing `inspection.py` / durable render
   jobs for reproducible before/after views, scene hashes, cameras, frames, lighting,
   color settings and seeds. Record GPU/CPU timing and memory on the RTX 5080. Compare
   measurements and captures; aesthetic acceptance remains an explicit human judgment.

Recommended next Codex task: connect Claude Code to this stdio service on the user's
Windows machine, run the full test commands with the exact Loopcut Blender 5.2.2 binary,
then validate the experimental Codex adapter using an existing local sign-in. A live
multi-specialist Loopcut integration remains separate from this bounded Asset Doctor tool.
