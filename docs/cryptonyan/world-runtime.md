# World assembly and Unreal runtime review — v0.7

This milestone connects audited runner kits into a longer route, assigns biomes and
places deterministic decorative posts outside the track. It includes an editor Python
placement adapter, an independent C++ platform actor for Unreal, and a small periodic
texture generator feeding the existing PBR batch pipeline.

Version 0.8 adds a [combined Blender preview and geometry report](world-preview.md)
using the same kits and world recipe, before proceeding to Unreal acceptance.

**Validation boundary:** Blender generation and textured publication run in cloud.
World composition and editor orchestration have portable tests. The C++ motion math
is compiled with a normal C++17 compiler and compared against the Python motion model.
The complete Unreal plugin has **not** been compiled with UnrealBuildTool/UHT or run in
UE 5.8 here. Its reflected APIs, editor materials, collision and rider behavior require
the local steps below. A passing fake-editor test is not an Unreal compatibility claim.

## Build reusable kits and connect them

Use a complete checkout and Python 3.11+. From PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .\scripts\addons_core).Path
$env:LOOPCUT_BLENDER = 'C:\Tools\Loopcut\blender.exe'
$work = Join-Path $env:LOCALAPPDATA 'CryptoNyanAssembly'
$inputs = Join-Path $work 'Kits'
New-Item -ItemType Directory -Force $inputs | Out-Null
New-Item -ItemType Directory -Force "$work\Receipts" | Out-Null

py -3.13 -m cryptonyan_asset_studio.runner_kit build `
  .\docs\cryptonyan\examples\world-short-kit.json `
  --destination "$inputs\short" --blender $env:LOOPCUT_BLENDER
py -3.13 -m cryptonyan_asset_studio.runner_kit build `
  .\docs\cryptonyan\examples\world-long-kit.json `
  --destination "$inputs\long" --blender $env:LOOPCUT_BLENDER
py -3.13 -m cryptonyan_asset_studio.world_assembly `
  .\docs\cryptonyan\examples\world-recipe.json `
  --source $inputs --report "$work\world-plan.json"
```

The short kit uses 12 m modules; the long kit uses 16 m modules. Both retain three
lanes and can contain high/low side branches and cyclic lifts. Their **ground-centre
entry and exit connectors** are assembled flush along +X. Lane widths and the complete
movement envelope must match. Every kit must have a model-certified route to its centre
exit, not merely to some final-row platform. The next kit's static first platform then
provides a continuous connection. Moving branches stay excluded from certification.

The plan binds the checked kit catalogs and import packages, lists connectors, module
references, placements, motion, biome and scale. One kit may be referenced by several
zones without duplicating its imported mesh. Input paths are relative to `$inputs`;
moving intact inputs to another root preserves the plan ID. Sources/receipts are never
overwritten. Maximum: 8 zones, 8 biomes, 16 decorations per zone and 512 actors overall.

This first connector library supports forward-facing cuboid kits with matching lane
widths. It does not yet generate turns, arbitrary socket rotations, tunnels, room graphs,
slopes, objective/reward graphs or World Partition streaming. The posts are scaled
instances of the module, with seed-derived positions/heights and **no collision**.
Their bounds stay outside all three lanes plus a 1 m clear band; posts may overlap one
another. This is a reusable decoration seam, not a finished environment-art generator.

## Generate biome maps and publish variants

```powershell
py -3.13 -m cryptonyan_asset_studio.biome_materials `
  .\docs\cryptonyan\examples\ice-palette.json --destination "$inputs\ice" --seed 42 --size 128
py -3.13 -m cryptonyan_asset_studio.biome_materials `
  .\docs\cryptonyan\examples\lava-palette.json --destination "$inputs\lava" --seed 43 --size 128
py -3.13 -m cryptonyan_asset_studio.theme_batch build `
  .\docs\cryptonyan\examples\world-themes.json --source $inputs `
  --destination "$work\Variants" --blender $env:LOOPCUT_BLENDER
py -3.13 -m cryptonyan_asset_studio.theme_batch check "$work\Variants"
```

The generator creates 8-bit RGB PNG base colour, greyscale roughness and tangent-space
OpenGL normals, plus a Material Doctor manifest and generator recipe. A periodic field
tiles in U/V; normals come from its analytic derivatives with PNG row direction
accounted for. Pixels sample cell centres, so first/last rows are neighbours in the
periodic field, not duplicate rows. Sizes are powers of two from 32 to 512.

Palettes specify **linear RGB**; base-colour PNG values are encoded to sRGB. The maps
are stylized authored patterns, not physically measured ice/lava, AI inference, unique
UV baking, or guaranteed seam-free results on arbitrary mesh UV seams. Different seeds
produce different patterns; materials can be shared across many assets through the
existing explicit assignment recipe. Generator metadata names the algorithm and seed.

No ComfyUI/GPU is used for this path. ComfyUI-generated bundles can still replace these
bundles through the existing PBR tools. Textured Unreal automatic apply remains blocked;
the world placement adapter below uses shared **constant biome materials**, not an
unvalidated automatic textured-material import.

## Install and compile the Unreal actor locally

Copy the directory `integrations/unreal/CryptoNyanRuntime` into your C++ project's
`Plugins` directory, choosing a new destination. Enable the plugin, Python Editor
Script Plugin, Editor Scripting Utilities and the glTF/Interchange importer.
With the UE 5.8-supported Visual Studio/toolchain installed, adapt these project names:

```powershell
$ue = 'C:\Program Files\Epic Games\UE_5.8'
& "$ue\Engine\Build\BatchFiles\Build.bat" CryptoNyanRunEditor Win64 Development `
  '-Project=D:\CryptoNyanRun\CryptoNyanRun.uproject' -WaitMutex
```

The plugin directory is independently authored MIT-licensed source, with its own
LICENSE. It links only Unreal Core/CoreUObject/Engine and does not include Loopcut/GPL
implementation files. The external Python/Blender tooling retains its existing GPL
headers. No Unreal SDK or engine binary is redistributed by this repository.

`ACryptoNyanPlatform` owns a visual mesh and a movable box collision component sized
from the cuboid's local bounds. Mesh collision is disabled. The box blocks Pawn and
Visibility queries, allows character step-up, and does not simulate rigid-body physics
or affect navigation. Decorative instances disable collision entirely. This collision
shape is appropriate only for our generated cuboids, not arbitrary imported art.

Vertical lifts use the existing triangle-wave contract in centimetres. Time is elapsed
world game time since BeginPlay/reset, not accumulated per-tick distance. Motion respects
world pause/time dilation. `ResetMotion()` returns a platform to its initial phase.
The actor ticks before physics, moves without a sweep, and has no multiplayer replication,
crushing response, obstruction avoidance or player-specific base-velocity policy.
Walking, jumping off a moving base and collision at maximum speed require controller tests.

## Import modules, then place the world

First import each module once with the existing checked importer. In Unreal's Python
console, adapt the paths and run the following Python (or save it as a local script):

```python
import sys, json
from pathlib import Path
sys.path.insert(0, r'C:\src\loopcut\scripts\addons_core')
from cryptonyan_asset_studio.world_assembly import plan_world
from cryptonyan_asset_studio.unreal_review import run_review_import
from cryptonyan_asset_studio.unreal_world import run_world_review, sample_runtime

inputs = Path(r'C:\Users\YOUR_USER\AppData\Local\CryptoNyanAssembly\Kits')
receipts = inputs.parent / 'Receipts'
recipe = json.loads(Path(r'C:\src\loopcut\docs\cryptonyan\examples\world-recipe.json').read_text())
plan = plan_world(recipe, inputs)
results = [run_review_import(inputs / module['kit'] / 'publication/manifest.json',
           receipts / (identity + '-import.json'), apply=True)
           for identity, module in plan['modules'].items()]
assert all(r['status'] == 'imported' for r in results), results
```

Already imported modules can be reused; do not rerun their exclusive import command.
Inspect an existing receipt/folder instead of deleting it to force a retry. The world
adapter loads the expected review mesh and rechecks its bounds, triangles, LOD, material
binding and absence of mesh collision before creating anything.

Create an **Empty Level**, save it as `/Game/CryptoNyan/ReviewMaps/Test`, and open it.
The adapter requires an otherwise empty level (WorldSettings is allowed) and this exact
explicit target. It never switches levels automatically. Then:

```python
result = run_world_review(recipe, inputs, receipts / 'world-review.json', apply=True,
                         target_level='/Game/CryptoNyan/ReviewMaps/Test')
assert result['status'] == 'placed_review_required', result
```

The new material folder is `/Game/CryptoNyan/WorldReviews/W_<world-id-prefix>`.
Materials are shared by biome, and mesh assets are shared by module. Each actor has
world/item tags, the correct phase-zero pose, scale and collision flag. Receipts record
owned actors/materials and partial failures. The adapter saves only its new materials;
**the level remains unsaved for review**. Inspect it, add lighting/player setup as
needed and save it explicitly before treating it as a reusable gameplay map.

An occupied map, existing world folder, missing plugin, wrong engine version, missing
mesh or mismatched module fails preflight. Later failures preserve owned partial results
and their receipt for inspection; there is no automatic rollback/delete/resume. A new
recipe/seed gives a different world ID. Planning works outside Unreal with no mutation:

```powershell
py -3.13 -m cryptonyan_asset_studio.unreal_world `
  .\docs\cryptonyan\examples\world-recipe.json --source $inputs `
  --report "$work\Receipts\world-dry-run.json"
```

## Local runtime acceptance

After compiling/loading the plugin and placing the level:

1. Save/reopen the review level. Check module dimensions, centres, connector joins,
   palette colours, decoration clearance and lift phase-zero locations.
2. Start Play In Editor. In the Python console, run `sample_runtime(plan)` at several
   points across a cycle. This checks tagged game-world actor positions against the
   portable formula with 2 cm tolerance and reports missing/duplicate actors. The
   sample is read-only; a passing sample **does not** validate collisions or playability.
3. With the actual CryptoNyanRun character, walk across both zone joins, stand on lifts,
   jump on/off them, test upper/lower branches, pause/resume and reset. Repeat at 30,
   60 and 120 fps, including the maximum motion settings you intend to ship. Verify
   movement-base attachment, inherited velocity and ceiling/obstacle behavior manually.
4. Check static and moving collision via visibility traces and the character capsule;
   decorations must not block it. The supplied collision is query-only and targets
   Pawn/Visibility, not a general physics simulation or custom collision-channel setup.
5. On Windows with the installed Loopcut binary, run `test_cryptonyan_assembly.py` and
   the complete `test_cryptonyan*.py` suite. Review generated normal orientation and
   repeated UV seams visually; test imported textured variants separately in UE 5.8.

The runtime sampler requires an active PIE game world. Its results are snapshots, not
a continuous robot playtest. Networked lifts, objective-based level graphs, phase-switch
platforms and the echo-cat mechanic remain future milestones.
