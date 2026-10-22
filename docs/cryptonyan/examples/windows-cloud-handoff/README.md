# Local Windows installation: sanitized cloud handoff

Snapshot: 2026-10-22. These files describe an existing installation; they are **examples**, not local executable configuration. No original workflow, configuration, model or game asset is included. Path aliases deliberately have no private mapping in this repository. No cloud session can reach the PC merely by reading this folder.

Read [inventory.json](inventory.json), [validation.json](validation.json), [workflow-index.json](workflow-index.json) and [dependencies.json](dependencies.json). [path-aliases.json](path-aliases.json) defines meanings, not values. This is a source update to Studio/MCP 0.40.0 at `2edb493a702573c55c686daf93823d66eac1b6e9`, including merged PR #40. The stock Blender 5.2.0 LTS binary is unchanged; the Loopcut addon still reports 0.2.5. PC-specific source adaptations remain private and uncommitted.

## Actual workflow exports

| API graph | Function and input | Output and evidence |
| --- | --- | --- |
| [trellis-active](workflows/trellis-active.api.json) | Multi-view TRELLIS/Pixal3D from one cropped reference sheet; original node IDs include 364 and 900 | Textured low-poly GLB, normals/AO and UV pipeline. Captured from an already running queue entry; completion not claimed. |
| [prep](workflows/prep.api.json) | Existing UV mesh and reference PNG | Normal/reference view sheets; historical successful receipt. |
| [pbr](workflows/pbr.api.json) | Existing UV mesh and reference; local Flux2 Klein and UltraTex | Albedo and metallic/roughness views, UV bake, GLB and previews; historical successful receipt. Normal conditions are not proof of an exported normal texture. |
| [rebake](workflows/rebake.api.json) | Same mesh/reference plus previously generated image sheets | Combined UV bake and preview; receipt status recorded in its manifest. |
| [oblique](workflows/oblique.api.json) | Existing sheets plus a rotated UltraTex rig | Refined views and combined bake; historical successful receipt. |
| [video](workflows/video.api.json) | Neutral replacement prompt and first frame; local MiniMax H3 weights, ClipProj and Turbo LoRA | Video with decoded audio; API graph extracted from existing MP4 metadata. No external MiniMax API call was made. |
| [audio](workflows/audio.api.json) | Replacement caption/lyrics; local MiniMax Music3 weights | Audio file; API graph extracted from existing compressed-audio metadata. Subgraph IDs such as `37:6` are preserved. |

Every graph has a companion JSON in `manifests/` listing function, required models, package bindings, input keys, output types/names, node IDs, changed example literals and execution evidence. `installed_file_present` means a file with that name exists under a scanned model root; it does **not** certify weights, license, successful loading or sufficient VRAM. `referenced_only_not_found_in_scanned_roots` means precisely that, not an instruction to download it. Installed package commits are measured now; they are not retroactively assigned to historical runs.

Prompts, lyrics, image names, mesh paths, output prefixes and UI titles were neutralized in copies. **Node IDs, class types, input keys and all graph links remain unchanged.** Numeric sampling parameters were retained. Consequently the examples need replacement input images/mesh and local alias resolution before use; sanitized copies have not been queued. No image/mesh is bundled. In particular rebake/oblique require prepared view sheets from prior stages. The alias syntax is documentation notation, not a feature that the server automatically expands.

The saved GUI library also contains Hunyuan3D, HYMotion, LTX2, Kandinsky and other templates. [saved-template-catalog.json](saved-template-catalog.json) records discovered node types without private names. A saved template is not a tested API graph. Their subgraph/widget bindings were not guessed or flattened. The exports above cover actual queued or previously produced local outputs, not every historical workflow variant.

The captured TRELLIS/Pixal3D graph uses the active ComfyUI core's `comfy_extras.nodes_trellis2` and mesh-processing modules. An installed extension named TRELLIS is not proof that this graph uses that extension. The measured `python_module` and package mapping in `dependencies.json` identify the nodes actually discovered.

## Connections and local binding

All files under `connections/` end in `.example.*`. Instantiate a **separate local copy** after replacing aliases with absolute paths. Keep private mappings and credentials outside Git. Use the existing Python, Blender, ComfyUI environment and model roots. The [agent connection example](connections/agent-connection.example.json) intentionally leaves `comfy_profiles` empty, matching the existing launcher's disabled texture integration. The [Comfy profile example](connections/comfy-profiles.example.json) starts with an empty profile list. It must be bound to a loopback HTTP endpoint supported by the local-only adapter. No authenticated URL or real endpoint is published.

The [Claude fragment](connections/claude-mcp.example.json) and [Codex fragment](connections/codex-mcp.example.toml) show the repository's isolated `mcp_launcher.py` interface, with separate per-client queues. They are examples of the current interface, **not exported account files and not a claim that global clients were reconfigured**. Existing local use still starts the preserved PowerShell stdio launcher. Do not replace unrelated MCP registrations or reuse one owned queue across simultaneous clients.

After local binding, use `agent_connect check <LOCAL_CONNECTION_PROFILE> --probe-mcp` as described in [agent-connections](../../agent-connections.md). A successful diagnostic checks a fresh process, not a persistent external-client connection. Actual validation here exercised the existing launcher, initialization, discovery, catalog, empty jobs and the PR40 guide. Twenty base tools were discovered; optional texture tools require configured profiles. The PBR GLB/atlas pipeline cannot be represented honestly as an ordinary PNG texture collector without additional reviewed channel/output bindings. TRELLIS needs the native mesh collector still listed as missing upstream.

## Scope and remaining validation

No generation was submitted, no model loaded for validation and no game asset changed. An existing ComfyUI TRELLIS job was left running. Blender addon registration, real Codex app-server initialization and the OptiX hardware profile passed without rendering or saving a scene/preferences. The updated MCP was started for a stdio handshake and closed afterwards; no previously running Loopcut MCP needed termination, and no persistent service is claimed.

See `validation.json` for exact suite scopes, skips, retained Windows fake-executable failures and remaining Unreal/ComfyUI/editor checks. PR40 provides Unreal runtime **source**, not an installed, compiled or gameplay-validated plugin. The full 871-test extension run preceded PR40; its 28 new tests and 32 Director tests passed separately after merging. The broader Codex fake-client suite remains non-passing on Windows; a successful real executable handshake does not replace a complete conversational run.

Privacy checks before publication cover this folder and the staged diff: private paths/usernames, authenticated URLs, private addresses, credential-like keys/values and personal prompts/lyrics. Only explicit documentation/example paths are staged. Original configurations, private history receipts, media, models, caches and game assets stay local. [privacy-review.json](privacy-review.json) records the performed checks without disclosing their private match inputs.
