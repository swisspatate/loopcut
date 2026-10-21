# Connected-world Blender preview and geometry checks

Version 0.8 builds a single portable `.blend` from the validated kits in a world
recipe. Open it to inspect all zones, biome colors, off-track decoration and moving
platforms together before the [Unreal review import](world-runtime.md).

The builder appends each module's existing mesh from a private snapshot, instances
it across zones, and overrides materials per object. It does not regenerate the
mesh or copy geometry per actor. Each zone gets its own collection. Colors are the
recipe's constant linear-RGB palettes, not the separately generated PBR textures.
There are no script drivers, source edits, external library links or Unreal writes.

## Build and inspect

First build `Kits/short` and `Kits/long` using the commands in
[world-runtime.md](world-runtime.md). The existing example world recipe is reused.
From the repository root on Linux:

```sh
export PYTHONPATH="$PWD/scripts/addons_core"
python3 -m cryptonyan_asset_studio.world_preview plan \
  docs/cryptonyan/examples/world-recipe.json \
  --source /tmp/CryptoNyan/Kits --destination /tmp/CryptoNyan/WorldQA
python3 -m cryptonyan_asset_studio.world_preview build \
  docs/cryptonyan/examples/world-recipe.json \
  --source /tmp/CryptoNyan/Kits --destination /tmp/CryptoNyan/WorldPreview \
  --blender /usr/bin/blender --timeout 120
python3 -m cryptonyan_asset_studio.world_preview check \
  /tmp/CryptoNyan/WorldPreview --source /tmp/CryptoNyan/Kits
```

Each destination must be new and outside the source root. `plan` writes the plan
and geometry report without Blender. `build` writes these plus `world-preview.blend`
and the success catalog `preview.json`. Structural/geometry errors prevent the
worker from launching; warnings allow a review build. A failed or timed-out build
leaves partial output without a valid success catalog. Inspect it, then select a
new destination to retry. The timeout bounds the Blender process; input validation
and snapshot copying happen before it. Inputs are limited to eight modules, eight
zones, 512 actors and 512 MiB of module snapshots.

`check` recomputes diagnostics and checks artifact hashes. Optional `--source`
also revalidates the original kits, plan and source hashes. Without it, checking is
portable and detects inconsistency within the output, not source provenance or a
maliciously rewritten catalog. Hashes are integrity records, not signatures.

In Blender open `world-preview.blend`, select all and use **Frame Selected**, then
play the timeline. Material Preview or Solid / Color Type / Material displays the
biome palette. UE centimetres become Blender metres with the Y axis reversed.

## Motion window

Frame 1 is time zero at 30 fps. All moving objects receive explicit linear Z keys
through twice the longest period, including subframe-correct extrema. Short-period
objects keep moving throughout the shared window. The maximum is 1,200 intervals
(frame 1 through 1,201). Different periods do not always share a loop boundary;
`preview.json.window.whole_world_loop` says whether this window closes all cycles.
Otherwise wrapping the timeline introduces a discontinuity in some objects; this
finite preview is not the unbounded Unreal runtime animation.

## Geometry report

The model is limited to the existing unrotated, axis-aligned runner cuboids. It uses
published module bounds, actor scale and UE centimetre coordinates. Positive
penetration greater than 0.001 cm on all three axes is an overlap; touching faces
and edges are allowed. Reports include actor pairs and penetration along each axis.

| Finding | Meaning | Build policy |
| --- | --- | --- |
| `static_overlap` | Two collision-enabled static cuboids penetrate | Error |
| `potential_motion_overlap` | Their full vertical sweep boxes intersect | Warning; timing/engine inspection required |
| `visual_overlap` | Overlap involving collision-disabled decoration | Warning |
| `connection_mismatch` | Zone endpoints, width, direction or connector metadata disagree | Error |
| `socket_geometry_mismatch` | Actual centre platform bounds do not meet the static ground socket | Error |
| `connection_count`, `missing_centre_route`, `world_extent_mismatch` | Inconsistent plan topology or endpoints | Error |

Only the first 256 findings are retained; severity counts cover **all** findings
and `findings_truncated` reports truncation. `geometry_passed` means no errors,
not no warnings. Swept boxes deliberately ignore relative phases: an intersection
is a potential risk and does not prove a simultaneous collision. These checks do
not model a player capsule, head clearance, jump timing, rider transport, navigation,
rotated meshes, physics, or material/visual quality. Engine, dynamics and controller
validation remain false. Existing static-route analysis stays in the source kits.

## Windows and Unreal acceptance still required

From a complete checkout in PowerShell, use the actual Loopcut Blender executable:

```powershell
$env:PYTHONPATH = "$PWD/scripts/addons_core"
$env:LOOPCUT_BLENDER = 'C:/path/to/Loopcut/blender.exe'
py -3.13 -m unittest discover -s loopcut/tests -p test_cryptonyan_preview.py -v
py -3.13 -m cryptonyan_asset_studio.world_preview build `
  docs/cryptonyan/examples/world-recipe.json `
  --source C:/CryptoNyan/Kits --destination C:/CryptoNyan/WorldPreview `
  --blender $env:LOOPCUT_BLENDER
py -3.13 -m cryptonyan_asset_studio.world_preview check `
  C:/CryptoNyan/WorldPreview --source C:/CryptoNyan/Kits
```

Open the file, inspect zone boundaries and palette assignment, and scrub moving
objects near the end of the shared window. Verify source hashes and Windows file
locking/cancellation with the actual packaged Blender version. The real cloud test
uses Linux Blender 4.3.2; portable Windows CI does not run Blender.

For UE 5.8 follow the plugin build, empty-map placement and PIE sampling steps in
[world-runtime.md](world-runtime.md). Compare the same time offsets and world axes;
then playtest the real controller, box collisions, step-up, rider movement and
inter-zone transitions. UHT/plugin compilation and these gameplay checks cannot be
validated by the Blender preview. Live ComfyUI/GPU generation remains separate.
