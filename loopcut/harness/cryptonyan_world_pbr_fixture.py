# SPDX-License-Identifier: GPL-3.0-or-later
"""Inspect actual packed texture bytes, node wiring and animated world instances."""
import hashlib
import math
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/addons_core"))
import bpy
from cryptonyan_asset_studio.blender_materials import validate_material
from cryptonyan_asset_studio.runner_kit import read_json
from cryptonyan_asset_studio.runner_motion import position_at
from cryptonyan_asset_studio.world_preview import validate_preview, preview_placement
from cryptonyan_asset_studio.world_materials import material_for

root = Path(sys.argv[sys.argv.index("--")+1])
catalog = validate_preview(root)
world, appearance = read_json(root / "world-plan.json"), read_json(root / "appearance.json")
# Open only the .blend in a fresh directory containing no external images.
with tempfile.TemporaryDirectory() as temp:
    scene_path = Path(temp) / "standalone.blend"
    shutil.copyfile(root / "world-preview.blend", scene_path)
    bpy.ops.wm.open_mainfile(filepath=str(scene_path), load_ui=False, use_scripts=False)
    scene = bpy.context.scene
    assert scene["cryptonyan_appearance_id"] == catalog["appearance_id"]
    assert len(scene.objects) == len(world["actors"])
    assert len({o.data.as_pointer() for o in scene.objects}) == len(world["modules"])
    assert not bpy.data.libraries and not bpy.data.texts
    actual_materials, actual_images, checked = {}, set(), set()
    for item in world["actors"]:
        obj = scene.objects[item["id"]]
        relative = material_for(appearance, world, item)
        material = obj.material_slots[0].material
        actual_materials.setdefault(relative, material)
        assert actual_materials[relative] == material
        assert obj.material_slots[0].link == "OBJECT" and obj["cryptonyan_material"] == relative
        assert max(abs(a-b) for a, b in zip(obj.scale, item["scale"])) < 1e-6
        if relative not in checked:
            checked.add(relative)
            spec = appearance["materials"][relative]
            assert validate_material(obj, material) == set(spec["channels"])
            images = [n.image for n in material.node_tree.nodes if n.type == "TEX_IMAGE"]
            assert {hashlib.sha256(bytes(i.packed_file.data)).hexdigest() for i in images} == {c["sha256"] for c in spec["channels"].values()}
            for image in images:
                assert not Path(bpy.path.abspath(image.filepath)).exists()
                # Blender lazily decodes packed images on first pixel access.
                sample = list(image.pixels[:16])
                assert sample and all(math.isfinite(v) for v in sample)
                assert image.has_data and len(image.pixels) == image.size[0]*image.size[1]*4
                actual_images.add(image.as_pointer())
    assert len({m.as_pointer() for m in actual_materials.values()}) == len(appearance["materials"])
    assert len(actual_images) == sum(len(m["channels"]) for m in appearance["materials"].values())
    for frame in (1, 79, 189, scene.frame_end-1):
        scene.frame_set(frame, subframe=.37)
        for item in world["actors"]:
            expected = position_at(preview_placement(item), (frame-1+.37)/30)
            actual = scene.objects[item["id"]].matrix_world.translation
            assert max(abs(a-b) for a, b in zip(actual, expected)) < 1e-4
print("CRYPTONYAN_WORLD_PBR_PASSED")
