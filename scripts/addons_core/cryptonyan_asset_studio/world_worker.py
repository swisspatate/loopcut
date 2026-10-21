# SPDX-License-Identifier: GPL-3.0-or-later
"""Private Blender worker: append only generated mesh data from verified snapshots."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.storage import digest, safe_path, write_json
from cryptonyan_asset_studio.runner_kit import read_json


def build(request, runtime):
    import bpy
    from cryptonyan_asset_studio.runner_motion import animate_preview
    from cryptonyan_asset_studio.world_geometry import analyze_world
    from cryptonyan_asset_studio.world_preview import preview_placement, preview_window
    from cryptonyan_asset_studio.world_materials import validate_appearance, material_for
    from cryptonyan_asset_studio.blender_materials import create_packed_material, validate_material

    root = Path(request["bundle"]).resolve(strict=True)
    path = safe_path(root, "world-plan.json")
    if digest(path) != request["plan_sha256"] or bpy.data.filepath:
        raise ValueError("Changed plan or non-factory scene")
    plan = read_json(path)
    if not analyze_world(plan)["geometry_passed"] or set(request["snapshots"]) != set(plan["modules"]):
        raise ValueError("Invalid world geometry or snapshots")
    appearance = None
    if request.get("appearance_sha256") is not None:
        appearance_path = safe_path(root, "appearance.json")
        if digest(appearance_path) != request["appearance_sha256"]:
            raise ValueError("Changed appearance plan")
        appearance = validate_appearance(read_json(appearance_path), safe_path(root, "textures"), plan)
    target = safe_path(root, "world-preview.blend")
    if target.exists():
        raise ValueError("Preview already exists")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    # Clear the unused factory cube mesh to preserve module names during append.
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    meshes = {}
    for key, spec in request["snapshots"].items():
        source = safe_path(runtime, spec["file"])
        if digest(source) != spec["sha256"]:
            raise ValueError("Changed snapshot")
        with bpy.data.libraries.load(str(source), link=False) as (available, appended):
            if "RunnerPlatformMesh" not in available.meshes:
                raise ValueError("Generated module mesh is missing")
            appended.meshes = ["RunnerPlatformMesh"]
        mesh = appended.meshes[0]
        mesh.calc_loop_triangles()
        lo, hi = plan["modules"][key]["import"]["asset"]["bounds_blender_m"]
        if len(mesh.vertices) != 8 or len(mesh.loop_triangles) != 12:
            raise ValueError("Unsupported preview module topology")
        corners = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        if any(not any(all(abs(v.co[i]-c[i]) < 1e-5 for i in range(3)) for v in mesh.vertices) for c in corners):
            raise ValueError("Module vertices differ from published bounds")
        meshes[key] = mesh
    materials = {}
    for name, palette in plan["recipe"]["biomes"].items():
        mat = bpy.data.materials.new("CN_"+name)
        mat.use_nodes = True
        mat.diffuse_color = (*palette["color_linear"], 1)
        mat.roughness = palette["roughness"]
        shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        shader.inputs["Base Color"].default_value = mat.diffuse_color
        shader.inputs["Roughness"].default_value = mat.roughness
        materials[name] = mat
    textured = {}
    if appearance is not None:
        for number, relative in enumerate(appearance["materials"]):
            textured[relative] = create_packed_material(safe_path(root / "textures", relative), name=f"CN_PBR_{number:02d}")
    checked_material_meshes = set()
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = "METRIC", 1.0
    scene.render.fps, scene.render.fps_base = 30, 1.0
    window = preview_window(plan)
    scene.frame_start, scene.frame_end = 1, window["frame_end"]
    collections = {}
    for zone in plan["zones"]:
        collection = bpy.data.collections.new(zone["id"]+"_"+zone["biome"])
        scene.collection.children.link(collection)
        collections[zone["id"]] = collection
    for item in plan["actors"]:
        mesh = meshes[item["module"]]
        if not mesh.materials:
            mesh.materials.append(next(iter(materials.values())))
        obj = bpy.data.objects.new(item["id"], mesh)
        collections[item["id"][:3]].objects.link(obj)
        placement = preview_placement(item)
        obj.location, obj.scale = placement["origin_m"], item["scale"]
        obj.material_slots[0].link = "OBJECT"
        obj.material_slots[0].material = materials[item["biome"]]
        if appearance is not None:
            relative = material_for(appearance, plan, item)
            obj.material_slots[0].material = textured[relative]
            obj["cryptonyan_material"] = relative
            pair = (item["module"], relative)
            if pair not in checked_material_meshes:
                validate_material(obj, textured[relative])
                checked_material_meshes.add(pair)
        obj.color = materials[item["biome"]].diffuse_color
        obj["cryptonyan_world_id"] = plan["world_id"]
        obj["cryptonyan_collision"] = item["collision"]
        obj["cryptonyan_kind"] = item["kind"]
        animate_preview(obj, placement, scene, duration_frames=window["frame_end"]-1)
    scene["cryptonyan_world_id"] = plan["world_id"]
    scene["cryptonyan_engine_validated"] = False
    scene["cryptonyan_whole_world_loop"] = window["whole_world_loop"]
    if appearance is not None:
        scene["cryptonyan_appearance_id"] = appearance["appearance_id"]
    scene.frame_set(1)
    bpy.context.view_layer.update()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(target), check_existing=False, copy=True)
    if digest(path) != request["plan_sha256"]:
        raise ValueError("World plan changed during worker execution")
    if appearance is not None:
        if digest(appearance_path) != request["appearance_sha256"]:
            raise ValueError("Appearance changed during worker execution")
        validate_appearance(appearance, root / "textures", plan)
    for spec in request["snapshots"].values():
        if digest(safe_path(runtime, spec["file"])) != spec["sha256"]:
            raise ValueError("World snapshot changed during worker execution")


if __name__ == "__main__":
    request_path = Path(sys.argv[sys.argv.index("--")+1]).resolve(strict=True)
    try:
        build(read_json(request_path), request_path.parent)
    except Exception as error:
        from cryptonyan_asset_studio.executors import WorkerFailure
        code = error.code if isinstance(error, WorkerFailure) else "invalid_asset" if isinstance(error, ValueError) else "blender_error"
        write_json(request_path.parent / "worker_error.json", {"code": code})
        raise SystemExit(1)
