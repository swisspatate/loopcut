# Asset Publisher v0.3 — Blender to Unreal review

Version 0.4 extends Blender publication with [packed PBR textures](material-pipeline.md).
The constant-material `/1` path described here is retained. Textured `/2` packages can
be planned for Unreal, but automatic apply is refused pending texture/material gates.

The `asset_publish` mission audits one explicitly named static mesh in an isolated
Blender snapshot, prepares a copy and exports a checked GLB. It returns three portable
files: `manifest.json`, `quality.json` and `SM_<name>_<hash>.glb`. The source `.blend`
is never saved. This path uses the existing queue, cancellation, deadlines, revisions,
MCP tools and optional Codex dispatcher; no upstream Loopcut agent loop is changed.

The Unreal import script is implemented, with an API probe and tests using a simulated
editor. **It has not been executed in Unreal 5.8.** Blender export and GLB roundtrip
are tested with real Blender 4.3.2. An engine import is a separate explicit local step;
publishing never launches or remotely controls Unreal.

## Supported first asset

- One saved `.blend`, one explicitly named visible mesh, at most 100,000 triangles by
  default (configurable success criterion within Asset Doctor limits).
- No modifiers, hierarchy, shape keys, rig/vertex groups, constraints, animation,
  linked/overridden data or instancing. Mirrored/degenerate transforms are rejected.
- Scene unit scale must be 1. Rotation and positive scale are baked into **copied mesh
  data**. Scene translation is removed; the source object's origin remains the asset
  pivot. Asymmetric geometry is tested to detect pivot/axis errors hidden by cubes.
- One opaque, constant Principled material: base color, metallic and roughness may
  vary; other inputs must remain at Blender defaults. No textures, groups, procedural
  shader nodes or multiple materials. A default material is supplied on the copy if
  the source has none. Material fidelity still requires visual review in Unreal.
- Source geometry only, one LOD, no game collision or sockets generated. The Unreal
  importer removes generated simple/convex collisions on the new review mesh and
  verifies zero before saving. These assets are not automatically gameplay-ready.

Unsupported objects fail with `publish_guard`; no usable package is returned. Failed
audit criteria return the audit report with `quality_passed=false` and no GLB/manifest.
ComfyUI textures, material baking, rigs/animations and automatic LOD/collision generation
remain subsequent work.

## Publish from Windows

From the full repository checkout in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$jobs = "$env:LOCALAPPDATA\CryptoNyanAssetStudio\publisher"
$blender = 'C:\Tools\Loopcut\blender.exe' # actual installed executable

$result = py -3.13 -m cryptonyan_asset_studio `
  --workspace $jobs --asset-root 'D:\CryptoNyan\AssetsToAudit' `
  --executor blender --blender $blender `
  publish platform.blend --object Platform --max-triangles 50000 | ConvertFrom-Json

$task = $result[0].task
$task.state
$task.quality_passed
$artifact = $task.artifacts | Where-Object { $_.path -like '*/manifest.json' }
$manifest = Join-Path (Join-Path $jobs $task.id) $artifact.path
```

Only resolve/use the manifest when state is `succeeded`, `quality_passed` is true and
the artifact exists. Exit status is 1 for failed execution or failed quality criteria.
For the Codex route use `--executor codex --codex C:\path\codex.exe` plus the Blender
argument. Real authenticated Codex dispatch still needs local validation; see
[codex-adapter.md](codex-adapter.md).

Equivalent mission JSON for `run` or MCP `mission_submit`:

```json
{
  "type": "asset_publish",
  "inputs": ["platform.blend"],
  "target_assets": ["Platform"],
  "constraints": {"timeout_seconds": 120, "max_attempts": 1},
  "success_criteria": {"max_triangles": 50000, "allow_warnings": true}
}
```

## Verify and plan without Unreal

Copy the three files together to a stable local package directory if transferring
between machines. Relative paths and hashes make the bundle relocatable. Do not edit
the manifest or put the import receipt inside the bundle.

```powershell
py -3.13 loopcut/harness/cryptonyan_unreal.py `
  --manifest $manifest --report 'D:\CryptoNyan\Reports\platform-plan.json'
```

The report directory must already exist. Each receipt path must be new; existing
receipts are never overwritten. This default dry run uses no Unreal API and changes
no project assets. Hashes establish consistency, not author identity or authenticity.

## Probe and import in the Unreal 5.8 editor

Use a test project first, with Python Editor Script Plugin, Editor Scripting Utilities
and the installed glTF/Interchange import support enabled. Run on the editor's main
thread, with one editor/writer using the project. No automatic plugin installation or
project configuration change is performed.

In the Unreal Python console (or a local Python script executed by the editor):

```python
import sys
sys.path.insert(0, r"C:\src\loopcut\scripts\addons_core")
import unreal
from cryptonyan_asset_studio.unreal_review import probe, run_review_import

print(probe(unreal))
result = run_review_import(
    r"D:\CryptoNyan\Packages\platform\manifest.json",
    r"D:\CryptoNyan\Reports\platform-import.json",
    apply=True,
    unreal_module=unreal,
)
print(result)
```

`apply=True` is the explicit mutation boundary. Before import, the script checks:
the complete bundle, engine version 5.8, required Python APIs, and absence of the
destination `/Game/CryptoNyan/Review/P_<package_id>`. It reserves that folder, submits
an automated synchronous `AssetImportTask` with overwrite/save disabled, and examines
the actual returned asset paths. Interchange may ignore `destination_name`; therefore
the receipt records actual paths instead of assuming a name.

Before saving any returned asset, the script checks one static mesh, triangle count,
one LOD, material binding, zero simple/convex collision and local bounds. Expected
conversion is Blender `(x, y, z)` metres to Unreal `(x, -y, z)` centimetres; bounds and
pivot differences block saving. Importer behavior must be confirmed locally. Material
appearance, UV quality, normals/tangents, Nanite, runtime physics and performance are
not certified by these numerical checks.

Failures leave their new review folder for inspection and record `failed_stage`,
`owned_assets`, `saved`, and measured differences. **This is not a transactional editor
rollback**: a save error can leave a subset saved; a crash can leave an incomplete
receipt. Existing review folders are refused even when a previous attempt failed.
No asset deletion, forced reimport, production replacement or automatic merge occurs.
The version/API probe does not prove that an installed glTF importer works.

## Required acceptance on the local installation

1. Run `py -3.13 -m unittest discover -s loopcut/tests -p 'test_cryptonyan*.py' -v`
   with `LOOPCUT_BLENDER` pointing to the actual Loopcut executable.
2. Create the reproducible asymmetric fixture with the harness:
   `blender.exe --background --factory-startup --disable-autoexec --python loopcut/harness/cryptonyan_fixture.py -- create_publish D:\CryptoNyan\AssetsToAudit\platform.blend`.
   Publish its `Platform` object. `Negative` and `Procedural` must fail explicitly.
3. Probe the actual Unreal version/APIs, then import into a disposable project.
   Check the returned receipt, four triangles, expected asymmetric bounds, pivot,
   material color/metallic/roughness and saved asset after reopening the project.
4. Repeat the same bundle import: it must refuse the existing folder. Modify a copied
   GLB byte: it must fail integrity validation before any editor mutation. Try an
   existing receipt path: it must refuse without overwriting it.
5. Test Windows long/Unicode paths, Blender cancellation/timeout and editor failure
   recovery. Engine imports run synchronously in the editor and are not cancellable
   through the Blender mission queue.

## Implementation and API references

`asset_publisher.py` reuses Loopcut `glb._expected`, `glb._export`, `parse`, `validate`,
`summary`, `compare` and `dropped_nodes`. Private helper compatibility is covered by
the real Blender fixtures and must be rechecked on upstream updates. `publication.py`
defines the versioned manifest and integrity gates; `unreal_review.py` handles local
planning, probing and imports; `loopcut/harness/cryptonyan_unreal.py` is the script entry.

API names were checked against Epic's [AssetImportTask Python reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AssetImportTask?application_version=5.7),
[StaticMesh Python reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/StaticMesh?application_version=5.7),
[StaticMeshEditorSubsystem reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/StaticMeshEditorSubsystem?application_version=5.7),
and [UE 5.8 AssetImportTask API](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Editor/UnrealEd/UAssetImportTask).
Documentation review and simulated tests are not a substitute for engine execution.
