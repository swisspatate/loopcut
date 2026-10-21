# Textured world previews — v0.9

The combined Blender preview can now show validated PBR maps instead of only constant
biome colors. Choose a material explicitly for each used **biome + kit** pair. A short
platform and a long platform in the same biome can have different textures; several
pairs can also share one bundle. Mesh instances and motion are preserved.

The input is an existing Material Doctor bundle (`cryptonyan.material/1`), such as
the [periodic biome generator](world-runtime.md) output or an explicitly packed set of
ComfyUI PNGs. No model call or automatic channel inference happens during this build.
The `asset.blend`/GLB outputs of a theme batch are not material-bundle inputs; reuse
the `material.json` bundles assigned by its recipe.

## Use the existing world example

First follow [world-runtime.md](world-runtime.md) to create `Kits/short`, `Kits/long`,
`Kits/ice/material.json` and `Kits/lava/material.json`. The new assignment recipe is:

```json
{
  "schema": "cryptonyan.world-materials/1",
  "bindings": [
    {"biome": "ice", "kit": "short", "material": "ice/material.json"},
    {"biome": "lava", "kit": "long", "material": "lava/material.json"}
  ]
}
```

Kit and material paths are relative to `--source`. Every biome/module pair actually
used by the world must appear exactly once; unknown, missing or duplicate assignments
are rejected. The same assignment applies to that pair's platforms and decorations.
Up to eight pairs are supported, matching the bounded world recipe. Per-actor overrides,
procedural shader graphs, UV remapping and texture blending are outside this contract.

Linux, from the repository root:

```sh
export PYTHONPATH="$PWD/scripts/addons_core"
python3 -m cryptonyan_asset_studio.world_preview plan \
  docs/cryptonyan/examples/world-recipe.json \
  --source /tmp/CryptoNyan/Kits --destination /tmp/CryptoNyan/PBRPlan \
  --materials docs/cryptonyan/examples/world-pbr-materials.json
python3 -m cryptonyan_asset_studio.world_preview build \
  docs/cryptonyan/examples/world-recipe.json \
  --source /tmp/CryptoNyan/Kits --destination /tmp/CryptoNyan/PBRWorld \
  --materials docs/cryptonyan/examples/world-pbr-materials.json \
  --blender /usr/bin/blender --timeout 120
python3 -m cryptonyan_asset_studio.world_preview check \
  /tmp/CryptoNyan/PBRWorld --source /tmp/CryptoNyan/Kits
```

Use a new destination outside `--source`. `plan` writes `appearance.json` with input
hashes and budgets but does not copy images or launch Blender. `build` additionally
stores checked snapshots under `textures/`, packs images into `world-preview.blend`,
and writes a `cryptonyan.world-preview/2` catalog only on success. Untextured builds
still produce v1 catalogs and old previews remain checkable.

Open `world-preview.blend` and use **Material Preview** or Rendered shading to see
the maps. In Solid shading, set **Color Type / Object** to show the biome palette.
Images are packed,
so the `.blend` can open on its own. Keep the full output directory for independent
hash verification: `check` needs the plan, catalog and texture snapshots. Optional
`--source` additionally checks current source kits and materials. It does not require
the assignment recipe to remain at its original CLI path.

To make different textures for two assets in one biome, generate a second bundle
with another seed or pack another explicit set of maps, then assign different
`material` paths to those two kit entries. The real integration test exercises
four zones, two meshes and three PBR bundles, including two ice variants and a lava
bundle shared by two module types. The world geometry identity stays unchanged when
only material assignments change; `appearance_id` records the resulting look.

## Texture and memory contract

Each bundle requires base color and may include roughness, metallic and OpenGL +Y
tangent normals. Channels use equal dimensions, validated noninterlaced 8-bit RGB/RGBA
PNGs (maximum 4096 × 4096). Base color uses sRGB; data maps use Non-Color. The worker
reuses the existing direct UV-to-Principled graph, with normal strength 1, repeat
extension and linear sampling. One finite UV layer is required. Roughness and metallic
must be greyscale RGB; a colored scalar map fails in Blender before saving the scene.
PNG alpha does not enable material transparency. Missing channels retain the existing
Principled defaults; no roughness/normal/metallic map is inferred from base color.

The planner limits unique source bytes (manifests included) to **64 MiB** and total
decoded pixels to **16,777,216** across instantiated image channels. One material
manifest is loaded once even when used by many actors. Distinct manifests count their
own decoded images even if the underlying PNG bytes match. The pixel budget corresponds
to at most 256 MiB of four-channel float image buffers; Blender, render buffers, GPU
copies and temporary decoding allocations add overhead. This is not a VRAM benchmark.

Assignments are sorted before hashing, so reordering them or relocating intact source
folders does not change `appearance_id`. Changing maps or assignments changes it.
Source textures and meshes are never saved. Snapshot mutation, corrupted maps or
worker failure leaves partial output without a valid success catalog. Hashes provide
integrity checking, not authenticity or artistic/physical correctness certification.

## Local acceptance

On Windows, from a complete checkout with the actual Loopcut Blender executable:

```powershell
$env:PYTHONPATH = "$PWD/scripts/addons_core"
$env:LOOPCUT_BLENDER = 'C:/path/to/Loopcut/blender.exe'
py -3.13 -m unittest discover -s loopcut/tests -p test_cryptonyan_world_materials.py -v
py -3.13 -m cryptonyan_asset_studio.world_preview build `
  docs/cryptonyan/examples/world-recipe.json `
  --source C:/CryptoNyan/Kits --destination C:/CryptoNyan/PBRWorld `
  --materials docs/cryptonyan/examples/world-pbr-materials.json `
  --blender $env:LOOPCUT_BLENDER
```

Inspect both biome variants in Material Preview, scrub the animated platforms and
open a copy of the `.blend` without external textures. Check normal orientation,
roughness, texel stretch on scaled decorations, memory use and visual quality with
the project's actual Blender/color-management/GPU setup. Existing cuboid UVs map
each face to 0..1; this does not guarantee equal texel density or seamless corners.

Cloud integration tests run real Linux Blender 4.3.2 and check packed bytes, color
spaces, graph wiring, mesh/material sharing, transforms, late subframes and standalone
reopening. Portable CI skips Blender explicitly. **No UE 5.8 material import or live
ComfyUI GPU generation is validated by these tests.** Automatic textured Unreal
import remains blocked until texture, material and engine-specific gates are implemented
and checked locally. Palette-based Unreal review continues unchanged.
