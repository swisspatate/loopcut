# SPDX-License-Identifier: GPL-3.0-or-later
"""Factory-scene worker for the creative kit; no existing .blend is opened."""
import math
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.creative_kit import ELEMENTS, PALETTES, plan, terrain_height
from cryptonyan_asset_studio.runner_kit import read_json
from cryptonyan_asset_studio.storage import digest, safe_path, write_json


def material(name, color, emission=0):
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1)
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = .65
    shader.inputs["Emission Color"].default_value = (*color, 1)
    shader.inputs["Emission Strength"].default_value = emission
    return mat


def box_mesh(name, boxes):
    import bpy
    vertices, faces = [], []
    corners = [(-1,-1,-1), (1,-1,-1), (1,1,-1), (-1,1,-1), (-1,-1,1), (1,-1,1), (1,1,1), (-1,1,1)]
    cube_faces = [(0,3,2,1), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
    for box in boxes:
        offset = len(vertices)
        vertices.extend(tuple(box["center"][i]+v[i]*box["size"][i]/2 for i in range(3)) for v in corners)
        faces.extend(tuple(offset+i for i in face) for face in cube_faces)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for loop, coord in zip(poly.loop_indices, ((0,0), (1,0), (1,1), (0,1))):
            uv.data[loop].uv = coord
    return mesh


def instance(name, mesh, location=(0,0,0), angle=0):
    import bpy
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler.z = math.radians(angle)
    return obj


def reset():
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = "METRIC", 1
    scene.render.fps = 30
    scene.frame_start, scene.frame_end = 1, 61
    bpy.context.preferences.filepaths.save_version = 0
    return scene


def save(path, kit_id):
    import bpy
    if path.exists():
        raise ValueError("Creative output already exists")
    bpy.context.scene["cryptonyan_kit_id"] = kit_id
    bpy.context.scene["cryptonyan_engine_validated"] = False
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False, copy=True)


def architecture(plan_data, root):
    from cryptonyan_asset_studio.blender_materials import create_packed_material, validate_material
    mat = (create_packed_material(root / "material/material.json", name="ArchitecturePBR")
           if (root / "material/material.json").exists() else material("Architecture", PALETTES[plan_data["recipe"]["biome"]]))
    meshes = {}
    for index, (name, boxes) in enumerate(plan_data["modules"].items()):
        mesh = box_mesh("CN_"+name, boxes)
        mesh.materials.append(mat)
        obj = instance(name, mesh, (index*5,0,0))
        obj["cryptonyan_module"] = name
        if (root / "material/material.json").exists():
            validate_material(obj, mat)
        meshes[name] = mesh
    return meshes


def environment(plan_data, root):
    import bpy
    from mathutils import Vector
    scene = bpy.context.scene
    spec = plan_data["recipe"]
    meshes = architecture(plan_data, root)
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for actor in plan_data["actors"]:
        obj = instance(actor["id"], meshes[actor["module"]], actor["location_m"], actor["yaw_degrees"])
        obj["cryptonyan_module"] = actor["module"]
    grid, size = spec["terrain_grid"], spec["terrain_size_m"]
    vertices = []
    for y in range(grid):
        for x in range(grid):
            a, b = (x/(grid-1)-.5)*size, (y/(grid-1)-.5)*size
            vertices.append((a,b,terrain_height(a,b,spec)-.22))
    faces = [(i,i+1,i+1+grid,i+grid) for y in range(grid-1) for x in range(grid-1) for i in [y*grid+x]]
    terrain = bpy.data.meshes.new("MountainMesh")
    terrain.from_pydata(vertices, [], faces)
    terrain.update()
    terrain.materials.append(material("Terrain", PALETTES[spec["biome"]]))
    instance("Mountains", terrain)
    water_vertices = [(-12+x*.25, -8+y, .15) for y in range(17) for x in range(17)]
    water_faces = [(i,i+1,i+18,i+17) for y in range(16) for x in range(16) for i in [y*17+x]]
    water_mesh = bpy.data.meshes.new("LiquidMesh")
    water_mesh.from_pydata(water_vertices, [], water_faces)
    water_mesh.update()
    liquid = instance("Liquid_"+spec["liquid"], water_mesh)
    liquid["cryptonyan_liquid_simulation"] = False
    liquid.data.materials.append(material("Liquid", ELEMENTS["fire" if spec["liquid"] == "lava" else "water"],
                                         2 if spec["liquid"] == "lava" else 0))
    liquid.shape_key_add(name="Basis")
    wave = liquid.shape_key_add(name="Wave")
    for point in wave.data:
        point.co.z += .12*math.sin(point.co.x*3+point.co.y)
    for frame, value in ((1,0), (16,1), (31,0), (46,1), (61,0)):
        wave.value = value
        wave.keyframe_insert("value", frame=frame)
    rng = random.Random(spec["seed"])
    for index, (element, color) in enumerate(ELEMENTS.items()):
        mat = material("FX_"+element, color, 3)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1)
        particle_mesh = bpy.context.object.data
        bpy.data.objects.remove(bpy.context.object, do_unlink=True)
        particle_mesh.materials.append(mat)
        center = Vector((index*3-8, -12, 1))
        for n in range(12):
            obj = instance(f"FX_{element}_{n:02}", particle_mesh)
            direction = Vector((math.cos(n*math.tau/12), math.sin(n*math.tau/12), .4))
            for frame in (1, 16, 31, 46, 61):
                t = (frame-1)%30/30
                obj.location = center+direction*(.2+t*1.5)
                obj.scale = (.12*(1-t),)*3
                obj.keyframe_insert("location", frame=frame)
                obj.keyframe_insert("scale", frame=frame)
        bpy.ops.mesh.primitive_torus_add(major_radius=.7, minor_radius=.06, location=center)
        portal = bpy.context.object
        portal.name = "Portal_"+element
        portal.rotation_euler.x = math.pi/2
        portal.data.materials.append(mat)
    crystal_mat = material("LivingCrystal", (.2,.8,.7), .5)
    for i in range(12):
        x,y = rng.uniform(-16,16), rng.uniform(10,16)
        bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=.25, radius2=0, depth=1.5,
                                       location=(x,y,terrain_height(x,y,spec)+.5))
        obj = bpy.context.object
        obj.name = f"GrowingCrystal_{i:02}"
        obj.data.materials.append(crystal_mat)
        for frame, scale in ((1,.65), (31,1), (61,.65)):
            obj.scale = (scale,)*3
            obj.keyframe_insert("scale", frame=frame)
    if spec["weather"] != "clear":
        weather_mesh = box_mesh("WeatherParticle", [{"center": [0,0,0], "size": [.025,.025,.3 if spec["weather"] == "rain" else .025]}])
        weather_mesh.materials.append(material("Weather", (.65,.75,.8)))
        for i in range(48):
            x,y,z = rng.uniform(-10,10), rng.uniform(-10,10), rng.uniform(3,12)
            obj = instance(f"Weather_{i:02}", weather_mesh)
            obj.location = (x,y,z)
            obj.keyframe_insert("location", frame=1)
            obj.location = (x+2,y,z-(10 if spec["weather"] == "rain" else 3))
            obj.keyframe_insert("location", frame=61)
    light = bpy.data.lights.new("Sun", "SUN")
    light.energy = plan_data["lighting"]["sun_energy"]
    sun = bpy.data.objects.new("Sun", light)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(90-plan_data["lighting"]["sun_angle"]), 0, -.5)
    world = bpy.data.worlds.new("CreativeWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = plan_data["lighting"]["world_strength"]
    scene.world = world
    for x in (-8,8):
        lamp = bpy.data.lights.new("Accent", "AREA")
        lamp.energy, lamp.color, lamp.shape, lamp.size = 800, ELEMENTS["electric"], "DISK", 5
        obj = bpy.data.objects.new("Accent", lamp)
        scene.collection.objects.link(obj)
        obj.location = (x,-6,6)
    camera_data = bpy.data.cameras.new("Overview")
    camera = bpy.data.objects.new("Overview", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (30,-38,28)
    camera.rotation_euler = (-camera.location+Vector((0,0,2))).to_track_quat("-Z","Y").to_euler()
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 960, 640, 100
    return {"objects": len(scene.objects), "terrain_vertices": len(vertices), "weather_particles": 0 if spec["weather"] == "clear" else 48,
            "liquid": "animated_surface_not_fluid_simulation", "fx_particles": 72}


def build(request):
    import bpy
    from cryptonyan_asset_studio.cat_rig import build_cat, validate_cat
    root = Path(request["bundle"]).resolve(strict=True)
    source = safe_path(root, "plan.json")
    plan_data = read_json(source)
    if bpy.data.filepath or digest(source) != request["plan_sha256"] or plan(plan_data["recipe"]) != plan_data:
        raise ValueError("Changed plan or non-factory scene")
    reset()
    architecture(plan_data, root)
    save(root / "architecture.blend", plan_data["kit_id"])
    reset()
    report = environment(plan_data, root)
    save(root / "environment.blend", plan_data["kit_id"])
    reset()
    rig, skin, actions = build_cat()
    report["cat"] = validate_cat(rig, skin)
    report["clips"] = list(actions)
    save(root / "cat.blend", plan_data["kit_id"])
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    skin.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(filepath=str(root / "cat.glb"), export_format="GLB", use_selection=True,
                              export_animations=True, export_animation_mode="ACTIONS",
                              export_force_sampling=True, export_frame_range=False)
    if digest(source) != request["plan_sha256"]:
        raise ValueError("Creative plan changed during generation")
    write_json(root / "worker-report.json", {**report, "engine_validated": False})


if __name__ == "__main__":
    request_path = Path(sys.argv[sys.argv.index("--")+1]).resolve(strict=True)
    try:
        build(read_json(request_path))
    except Exception as error:
        import traceback
        traceback.print_exc()
        write_json(request_path.parent / "worker_error.json", {"code": "invalid_asset" if isinstance(error, ValueError) else "blender_error"})
        raise SystemExit(1)
