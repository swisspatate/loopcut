# PBR and ComfyUI pipeline — v0.4

For agent-driven generation using configured model/workflow profiles, see the
[v0.10 MCP profile guide](comfy-agent-profiles.md). The explicit CLI below remains supported.

This milestone implements local ComfyUI HTTP jobs, a portable Material Doctor,
non-destructive material application in Blender, and textured GLB publication. It
reuses the mission queue, isolated Blender worker and Loopcut's glTF exporter/checks.
No custom nodes, models, other GitHub projects or Python dependencies are installed.

The stages are separate explicit commands:

```text
approved ComfyUI API workflow → durable prompt receipt → saved PNGs + generation.json
   → explicit channel assignment → Material Doctor bundle → new packed .blend
   → existing asset_publish mission → checked, self-contained GLB + manifest + audit
   → Unreal dry-run plan → local manual material review
```

ComfyUI is an external local service, not a new mission executor or a native Loopcut
tool. Its jobs are not controlled by the Blender queue's cancellation/deadlines.
The generated image is not automatically a usable PBR texture. The caller chooses
channels; this implementation neither invents normal/roughness maps nor judges their
physical correctness, seams or artistic quality.

## 1. Configure the local ComfyUI connection

Use Python 3.11+ from a complete checkout. In PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$env:LOOPCUT_BLENDER = 'C:\Tools\Loopcut\blender.exe'
$work = Join-Path $env:LOCALAPPDATA 'CryptoNyanMaterials'
New-Item -ItemType Directory -Force $work | Out-Null
```

Start your already installed, trusted ComfyUI on `127.0.0.1:8188`. Export a workflow
in **API format** as `$work\workflow-api.json`. UI graph JSON is not the API graph.
Check the actual nodes, inputs, local model files and output nodes first. A workflow
may execute installed custom-node Python: its hash is approval of that exact graph,
not a sandbox or a guarantee about custom nodes/server hooks.

Create the configuration with the hash of canonical JSON and the real sampler's
seed binding (replace node `3` below if your graph uses another ID). The source
workflow must contain an integer in each declared seed input:

```powershell
$workflowHash = py -3.13 -c "import json,sys; from cryptonyan_asset_studio.comfyui_adapter import workflow_digest; print(workflow_digest(json.load(open(sys.argv[1],encoding='utf-8-sig'))))" "$work\workflow-api.json"
@{
  endpoint = 'http://127.0.0.1:8188'
  workflow_sha256 = $workflowHash.Trim()
  seed_inputs = ,@('3', 'seed')
  models = @()
} | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 "$work\comfy.json"
```

UTF-8 JSON with or without a BOM is accepted. A configuration
example is in [examples/comfy-config.json](examples/comfy-config.json); its placeholder
hash intentionally does not approve any workflow. Every model declaration, when supplied,
contains `name`, the local weight file's `sha256`, `license` and `attribution` strings.
Hashes can be measured with `Get-FileHash -Algorithm SHA256`. The HTTP API does not
attest which weight bytes/custom nodes ran: receipts label these **user declarations**,
with `model_provenance_verified=false` and `distribution_approved=false`. Empty/unknown
provenance never implies permission to distribute. Keep receipts with review assets.

Only literal loopback IPs and an explicit port are accepted. Proxy environment variables
and redirects are disabled. Remote/authenticated endpoints are outside this implementation.
Use a private workspace and one process at a time; an OS lock prevents concurrent receipt
writers. This assumes a trusted local ComfyUI server and trusted, reviewed workflows.

## 2. Submit, follow and collect

```powershell
$submitted = py -3.13 -m cryptonyan_asset_studio.comfyui_adapter `
  --config "$work\comfy.json" --workspace "$work\jobs" `
  submit "$work\workflow-api.json" --seed 12345 --timeout 600 | ConvertFrom-Json
$prompt = $submitted.prompt_id

py -3.13 -m cryptonyan_asset_studio.comfyui_adapter `
  --config "$work\comfy.json" --workspace "$work\jobs" status $prompt
py -3.13 -m cryptonyan_asset_studio.comfyui_adapter `
  --config "$work\comfy.json" --workspace "$work\jobs" wait $prompt
py -3.13 -m cryptonyan_asset_studio.comfyui_adapter `
  --config "$work\comfy.json" --workspace "$work\jobs" collect $prompt "$work\images"
```

`wait` exits nonzero if it does not observe success. Its budget applies to that CLI wait,
not server execution; a timeout leaves the job running. Each HTTP operation has a 10s
timeout and bounded response size; a final status poll can extend the wait by up to two
HTTP timeouts. No automatic resubmission occurs. If the submit response is lost, inspect
the `uncertain` receipt and server queue before retrying. Current ComfyUI accepts a client
`prompt_id`; a server that returns another ID is rejected, and its accepted job may need
manual inspection. Seeds do not guarantee bit-identical results across models/devices.

Only successful history entries can be collected. Up to 16 saved `output` PNGs, at most
32 MiB each/128 MiB total, are validated before creating a new destination. Images are
renamed `image-00.png`, etc.; `generation.json` maps these to node/output indices and
records byte hashes, submitted workflow, seed and declarations. Nothing is overwritten.
JPEG, video, previews, input files and API-returned path traversal are rejected.

`cancel PROMPT_ID` requests deletion of that one **queued** prompt. Running cancellation
must be done in ComfyUI. The adapter never calls `/interrupt`, whose older implementations
ignore prompt IDs. A deleted/evicted/unobserved job is `unknown`, not reported as success
or proven cancellation. A queue-to-running race can leave the prompt running; inspect
status/UI after deletion. No history deletion or global queue clear is performed.

## 3. Material Doctor and Blender copy

Create `$work\channels.json` mapping intended roles to relative image files, for example:

```json
{"base_color":"image-00.png","normal":"image-01.png","roughness":"image-02.png","metallic":"image-03.png"}
```

Use only the channels you actually generated. `base_color` is required in a bundle;
the other three are optional. A single colour output only needs `base_color`.

```powershell
py -3.13 -m cryptonyan_asset_studio.materials pack `
  --source "$work\images" --channels "$work\channels.json" --destination "$work\material"
py -3.13 -m cryptonyan_asset_studio.materials check "$work\material\material.json"

& $env:LOOPCUT_BLENDER --background --factory-startup --disable-autoexec --threads 1 `
  --python-exit-code 1 --python .\loopcut\harness\cryptonyan_material.py -- `
  --source "$work\platform.blend" --bundle "$work\material\material.json" `
  --object Platform --output "$work\platform-pbr.blend"

py -3.13 -m cryptonyan_asset_studio --workspace "$work\publish-jobs" `
  --asset-root $work --executor blender --blender $env:LOOPCUT_BLENDER `
  publish platform-pbr.blend --object Platform
```

The named mesh must already have exactly one UV map. Material application copies its
mesh data, replaces the material in the new scene copy, embeds validated image bytes,
and saves only the new destination. It checks source hashes and refuses existing output
paths. An interrupted operation may leave a partial reserved destination; inspect it
before choosing a fresh filename. It does not perform unwrap, bake, retopology or repair.

The material manifest stores channel hashes. A copy is also embedded as a material custom
property in the staged `.blend`. Keep `generation.json`, the material bundle and staged
scene together to trace those channel hashes back to ComfyUI. The publication manifest
describes the **exported** texture bytes; the exporter may repack/reencode them, so hashes
need not equal the original PNG hashes. Full generation receipts are not embedded in GLB.

Supported material envelope:

- Opaque, single Principled material; base colour in sRGB, scalar maps and normals in
  Non-Color. Normals are tangent-space **OpenGL +Y**, strength 1. No automatic DirectX flip.
- Complete 8-bit RGB/RGBA, noninterlaced PNGs, 1–4096 pixels per side, matching dimensions.
  PNG CRCs, decoded byte budget and row filters are checked. Greyscale/palette/16-bit/APNG
  inputs must first be explicitly converted outside this tool.
- Direct UV image connections, linear filtering/repeat, exactly one UV layer. Roughness
  and metallic use scalar image channels; greyscale content replicated across RGB is required and checked in Blender.
  glTF packs roughness into G and metallic into B; AO/height/displacement are unsupported.
- Packed images only. External file dependencies, dirty images, texture coordinate/mapping
  nodes, procedural shaders, extra nodes, multiple materials and unsupported Principled
  features fail closed. Existing static geometry restrictions still apply.

Constant materials retain `cryptonyan.publication/1`. Textured assets use `/2` and
`policy.textures=embedded_png`; `textures` lists actual GLB image indices, roles, SHA-256,
dimensions, byte counts and colour-space interpretation. The loader checks the inventory
against the embedded bytes, material bindings and UVs, as well as the existing geometry,
source/audit and package integrity checks. There are still exactly three output files.

## Unreal and local acceptance

The existing [Unreal harness](publisher.md) can produce a dry-run plan for `/2` packages,
including texture inventory. It marks `automatic_apply_supported=false`. Explicit apply
refuses textured packages before creating any editor folder: automatic imported texture
settings and material-graph validation are not yet implemented. Constant `/1` imports keep
their prior behavior. For manual review, import the GLB into a **new** temporary UE folder.

Required local checks, not established by cloud tests:

1. Actual ComfyUI installation on Windows/RTX 5080: accepted client IDs, intended models,
   seed binding, history/output nodes, PNG retrieval, interrupted/queued jobs, VRAM/time.
   Do not assume a model fits 16 GB. No GPU generation ran in cloud.
2. Installed Loopcut executable: run `test_cryptonyan*.py`, prepare/publish a UV-mapped
   mesh, verify source hashes and visually inspect textures/tangent normals/seams.
3. Unreal 5.8 glTF/Interchange: verify material connections, sRGB flags, packed roughness
   G/metallic B, normal convention/import conversion/compression, dimensions, pivot, scale
   and appearance. Implement measurable texture/material gates before enabling automation.
4. Authenticated Codex and Claude Code MCP are the separate existing local acceptance
   items. This milestone does not claim they have been exercised with user credentials.

Protocol reference inspected: [ComfyUI server.py at 7a28332](https://github.com/Comfy-Org/ComfyUI/blob/7a28332047b6af638dc6c7f72ef3481a718769fd/server.py),
`POST /prompt`, `GET /history/{prompt_id}`, `GET/POST /queue`, `GET /view`.
This is a documented source revision, not a forced install or proof of your server version.

## Subsequent integrations

The following remain a roadmap, not installed integrations:

| Project | Proposed next adapter | Required gate |
| --- | --- | --- |
| [Material Maker](https://github.com/RodZill4/material-maker) | Produce the same explicit PBR bundle from procedural materials | Verify supported export automation and pin a version |
| [PCGEx](https://github.com/PCGEx/PCGExtendedToolkit) | Assemble modular runner sections from seeded graphs | Stable UE 5.8 branch, sockets/pivots, collision and jump validation |
| Blender Rigify / [UniRig](https://github.com/VAST-AI-Research/UniRig) | Controlled quadruped rig, then assisted skeleton/weights | Cat anatomy, paw contacts, tail, root motion; separate model licence/dependency checks |
| [meshoptimizer](https://github.com/zeux/meshoptimizer) | Optional LOD preparation and measurable simplification | Silhouette/UV error, game budgets and Unreal import compatibility |
| [Infinigen](https://github.com/princeton-vl/infinigen) | Procedural scenery candidates | Game-scale topology/material budgets and conversion |
| [Wan2.2](https://github.com/Wan-Video/Wan2.2) | Reference clips and promotional video jobs | Measured memory/runtime and model/output provenance |

Integrate these through adapters and portable manifests, preserving each project's own
installation and licence boundaries. The immediate next engineering step is the actual
UE texture gate plus a verified Material Maker export path, followed by modular PCGEx.
