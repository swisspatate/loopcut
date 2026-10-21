# SPDX-License-Identifier: GPL-3.0-or-later
"""Private factory-started Blender worker. Generates assets only in its new bundle."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.storage import digest, safe_path, write_json


def build(request):
    import bpy
    from cryptonyan_asset_studio.asset_doctor import audit_blender
    from cryptonyan_asset_studio.asset_publisher import export_static_mesh
    from cryptonyan_asset_studio.publication import seal_manifest
    from cryptonyan_asset_studio.procedural_level_builder import validate_layout, analyze_layout
    from cryptonyan_asset_studio.schema import Mission
    from cryptonyan_asset_studio.runner_kit import read_json, validate_bundle

    root = Path(request["bundle"]).resolve(strict=True)
    layout_path = safe_path(root, "layout.json")
    if digest(layout_path) != request["layout_sha256"]:
        raise ValueError("Layout changed before worker startup")
    layout = validate_layout(read_json(layout_path))
    if not analyze_layout(layout)["model_passed"]:
        raise ValueError("Runner movement preflight failed")
    # This worker owns a factory scene and a new directory; no user scene is loaded.
    if bpy.data.filepath:
        raise ValueError("Runner worker requires a fresh unsaved scene")
    for name in ("modules.blend", "preview.blend", "publication", "kit.json"):
        if safe_path(root, name).exists():
            raise ValueError("Runner output already exists")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    bpy.context.preferences.filepaths.save_version = 0
    length, width, thickness = layout["module"]["size_m"]
    vertices = [(0, -width/2, -thickness), (length, -width/2, -thickness),
                (length, width/2, -thickness), (0, width/2, -thickness),
                (0, -width/2, 0), (length, -width/2, 0), (length, width/2, 0), (0, width/2, 0)]
    mesh = bpy.data.meshes.new("RunnerPlatformMesh")
    mesh.from_pydata(vertices, [], [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                                  (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for index, value in zip(polygon.loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
            uv.data[index].uv = value
    obj = bpy.data.objects.new("RunnerPlatform", mesh)
    bpy.context.scene.collection.objects.link(obj)
    for key in ("entry_m", "exit_m", "entry_normal", "exit_normal"):
        obj["cryptonyan_" + key] = layout["module"][key]
    material = bpy.data.materials.new("M_RunnerPlatform")
    material.use_nodes = True
    shader = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = (0.08, 0.4, 0.65, 1)
    shader.inputs["Roughness"].default_value = 0.65
    mesh.materials.append(material)
    bpy.context.view_layer.update()
    source = safe_path(root, "modules.blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(source), check_existing=False, copy=True)
    source_hash = digest(source)
    publication = safe_path(root, "publication")
    publication.mkdir()
    mission = Mission.parse({"type": "asset_publish", "inputs": ["modules.blend"], "target_assets": [obj.name]})
    audit = audit_blender(mission.target_assets, mission.success_criteria)
    if not audit["passed"]:
        raise ValueError("Generated module failed Asset Doctor")
    manifest = export_static_mesh(mission, source, publication, audit)
    write_json(publication / "quality.json", {"schema": "cryptonyan.quality-batch/1", "passed": True, "reports": [audit]})
    seal_manifest(manifest, publication)
    for placement in layout["placements"]:
        instance = bpy.data.objects.new(placement["id"], mesh)
        instance.location = placement["origin_m"]
        instance["cryptonyan_layout_id"] = layout["layout_id"]
        instance["cryptonyan_lane"] = placement["lane"]
        bpy.context.scene.collection.objects.link(instance)
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(root / "preview.blend"), check_existing=False, copy=True)
    if digest(source) != source_hash or digest(layout_path) != request["layout_sha256"]:
        raise ValueError("Runner source changed during build")
    files = ["layout.json", "analysis.json", "pcg-points.csv", "preview.svg", "modules.blend", "preview.blend",
             "publication/quality.json", "publication/manifest.json", "publication/" + manifest["asset"]["file"]]
    catalog = {"schema": "cryptonyan.runner-kit/1", "layout_id": layout["layout_id"], "module": layout["module"],
               "engine_validated": False, "files": {name: {"sha256": digest(safe_path(root, name)),
               "bytes": safe_path(root, name).stat().st_size} for name in files}}
    write_json(root / "kit.json", catalog)
    validate_bundle(root)


if __name__ == "__main__":
    request_path = Path(sys.argv[sys.argv.index("--") + 1]).resolve(strict=True)
    try:
        build(json.loads(request_path.read_text(encoding="utf-8")))
    except Exception as error:
        from cryptonyan_asset_studio.executors import WorkerFailure
        code = error.code if isinstance(error, WorkerFailure) else "invalid_asset" if isinstance(error, ValueError) else "blender_error"
        write_json(request_path.parent / "worker_error.json", {"code": code})
        raise SystemExit(1)
