# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender factory-scene worker for explicit image reconstruction recipes."""
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.image_workshop import load_bundle
from cryptonyan_asset_studio.creative_worker import box_mesh, instance, material, reset, save
from cryptonyan_asset_studio.storage import safe_path, write_json


def build(root):
    import bpy
    from mathutils import Vector
    from loopcut import glb
    from bpy_extras.object_utils import world_to_camera_view

    root = Path(root).resolve(strict=True)
    if bpy.data.filepath:
        raise ValueError("Image worker requires a factory scene")
    plan = load_bundle(root / "inputs")
    recipe = plan["recipe"]
    for filename in ("candidate.blend", "candidate.glb", "render.png", "geometry.json"):
        if (root / filename).exists():
            raise ValueError("Candidate output already exists")
    scene = reset()
    # All imported image data must travel with the editable scene.
    bpy.context.preferences.filepaths.use_file_compression = True
    objects = []
    for part in recipe["parts"]:
        shape = part["shape"]
        if shape == "box":
            obj = instance(part["id"], box_mesh(part["id"], [{"center": [0, 0, 0], "size": part["size_m"]}]))
        elif shape in ("cylinder", "cone"):
            bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=.5, radius2=.5 if shape == "cylinder" else 0, depth=1)
            obj = bpy.context.object
            for v in obj.data.vertices:
                v.co = Vector([v.co[i]*part["size_m"][i] for i in range(3)])
        else:
            before = set(bpy.data.objects)
            path = safe_path(root / "inputs", plan["sources"][part["source"]]["file"])
            bpy.ops.import_scene.gltf(filepath=str(path))
            imported = set(bpy.data.objects)-before
            if len(imported) != 1:
                raise ValueError("Source did not import as one object")
            obj = imported.pop()
            if obj.type != "MESH" or obj.modifiers or obj.data.shape_keys or obj.parent or obj.animation_data:
                raise ValueError("Source has unsupported runtime geometry")
            if len(obj.data.vertices) > 600000 or sum(len(p.vertices)-2 for p in obj.data.polygons) > recipe["triangle_budget"]:
                raise ValueError("Imported geometry exceeds budget")
            # Bake the glTF import's axis conversion, then fit the declared local box.
            obj.data.transform(obj.matrix_world)
            from mathutils import Matrix
            obj.matrix_world = Matrix.Identity(4)
            points = [v.co.copy() for v in obj.data.vertices]
            if not points or any(not math.isfinite(c) for p in points for c in p):
                raise ValueError("Invalid imported positions")
            low, high = [min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]
            if min(b-a for a, b in zip(low, high)) < .000001:
                raise ValueError("Source must have nonzero volume bounds")
            scale = [part["size_m"][i]/(high[i]-low[i]) for i in range(3)]
            center = Vector([(a+b)/2 for a, b in zip(low, high)])
            obj.data.transform(Matrix.Diagonal((*scale, 1)) @ Matrix.Translation(-center))
        obj.name = part["id"]
        if obj.name != part["id"]:
            raise ValueError("Part name collision")
        obj.location = part["position_m"]
        obj.rotation_euler = (0, 0, math.radians(part["yaw_deg"]))
        obj["cryptonyan_reference_sha256"] = plan["reference"]["sha256"]
        if shape != "glb":
            obj.data.materials.append(material(part["id"]+"_Material", part["color"]))
        obj.data.update()
        objects.append(obj)
    bpy.context.view_layer.update()
    expected = glb._expected(objects)
    triangles = sum(v["tris"] for v in expected.values())
    if (not 1 <= triangles <= recipe["triangle_budget"] or len(expected) != len(objects) or
            sum(len(o.data.vertices) for o in objects) > 600000):
        raise ValueError("Final geometry exceeds budget or contains empty parts")
    from cryptonyan_asset_studio.asset_doctor import audit_blender, MAX_VERTICES, MAX_FACES, MAX_CORNERS
    if all(len(o.data.vertices) <= MAX_VERTICES and len(o.data.polygons) <= MAX_FACES and
           len(o.data.loops) <= MAX_CORNERS for o in objects):
        audit = audit_blender([o.name for o in objects])
    else:
        audit = {"status": "skipped_complexity_budget", "passed": False}
    write_json(root / "asset-doctor.json", audit)
    camera_spec = recipe["camera"]
    data = bpy.data.cameras.new("ReferenceCamera")
    camera = bpy.data.objects.new("ReferenceCamera", data)
    scene.collection.objects.link(camera)
    camera.location = camera_spec["position_m"]
    camera.rotation_euler = (Vector(camera_spec["target_m"])-camera.location).to_track_quat("-Z", "Y").to_euler()
    data.type, data.lens, data.ortho_scale = camera_spec["projection"], camera_spec["lens_mm"], camera_spec["ortho_scale_m"]
    data.clip_start, data.clip_end = .001, 5000
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device, scene.cycles.samples, scene.cycles.seed = "CPU", camera_spec["samples"], 0
    scene.cycles.use_denoising = False
    scene.render.resolution_x, scene.render.resolution_y = camera_spec["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format, scene.render.image_settings.color_mode = "PNG", "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure, scene.view_settings.gamma = 0, 1
    world = bpy.data.worlds.new("ReferenceWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (.15, .15, .15, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .5
    scene.world = world
    light_data = bpy.data.lights.new("ReferenceSun", "SUN")
    light_data.energy, light_data.angle = 3, .1
    sun = bpy.data.objects.new("ReferenceSun", light_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (.5, -.4, -.5)
    bpy.context.view_layer.update()
    # Framing evidence is geometric only: it says nothing about occlusion/fidelity.
    clipped = []
    for obj in objects:
        projected = [world_to_camera_view(scene, camera, obj.matrix_world @ Vector(c)) for c in obj.bound_box]
        if any(p.z <= data.clip_start or p.z >= data.clip_end or not 0 <= p.x <= 1 or not 0 <= p.y <= 1 for p in projected):
            clipped.append(obj.name)
    report = {"schema": "cryptonyan.image-geometry/1", "plan_identity": plan["identity"],
              "blender": bpy.app.version_string, "triangles": triangles, "objects": expected,
              "camera": camera_spec, "bounding_boxes_outside_camera": clipped,
              "asset_doctor_passed": audit["passed"],
              "render": {"engine": "CYCLES", "device": "CPU", "seed": 0, "view_transform": "Standard",
                         "look": "None", "exposure": 0, "gamma": 1, "sun_energy": 3, "world_strength": .5},
              "collision": "none", "lod": "source_only", "visual_quality_validated": False, "engine_validated": False}
    scene["cryptonyan_image_plan_identity"] = plan["identity"]
    bpy.ops.file.pack_all()
    save(root / "candidate.blend", recipe["id"])
    glb._export(root / "candidate.glb", objects)
    doc, binary = glb.parse((root / "candidate.glb").read_bytes())
    if glb.validate(doc, binary) or glb.compare(glb.summary(doc), expected) or glb.dropped_nodes(objects):
        raise ValueError("Export does not preserve supported geometry/material nodes")
    scene.render.filepath = str(root / "render.png")
    bpy.ops.render.render(write_still=True)
    write_json(root / "geometry.json", report)


if __name__ == "__main__":
    build(Path(sys.argv[sys.argv.index("--")+1]))
