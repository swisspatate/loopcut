# SPDX-License-Identifier: GPL-3.0-or-later
"""Seeded modular room graphs with mandatory checkpoints and declared clearance."""
import argparse
import copy
import csv
import hashlib
import html
import io
import json
import math
from pathlib import Path
import shutil
import struct
import threading
import time

from loopcut import glb
from .animation_doctor import exact, number, read_json
from .creative_director import identifier, integer, vector, recipe as director_recipe
from .executors import ExecutionContext, run_process
from .image_workshop import identity, inspect_source
from .publication import _hash
from .reference_board import _separate
from .storage import digest, safe_path, write_json
from .unreal_material_variants import _object_path

SIDES = ("east", "north", "west", "south")
DELTAS = ((1, 0), (0, 1), (-1, 0), (0, -1))
MAX_SOURCES = 128 * 1024 * 1024


def _cell(value, width, height):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Expected grid cell x/y")
    integer(value[0], 0, width-1); integer(value[1], 0, height-1)
    return tuple(value)


def _tags(values):
    if not isinstance(values, list) or len(values) > 8 or len(set(values)) != len(values):
        raise ValueError("Use up to eight distinct module tags")
    for value in values: identifier(value)
    return values


def specification(value):
    value = copy.deepcopy(value)
    exact(value, ("schema", "id", "seed", "grid", "start", "goal", "waypoints", "blocked", "route_cells",
                  "branches", "loops", "required_tags", "player", "search_budget", "anchor_m", "destination", "target_level"))
    if value["schema"] != "cryptonyan.modular-level/1":
        raise ValueError("Unsupported modular level recipe")
    identifier(value["id"]); integer(value["seed"], 0, 2**32-1)
    exact(value["grid"], ("width", "height"))
    width = integer(value["grid"]["width"], 2, 12)
    height = integer(value["grid"]["height"], 2, 12)
    start, goal = _cell(value["start"], width, height), _cell(value["goal"], width, height)
    if start == goal: raise ValueError("Choose distinct start and goal")
    if not isinstance(value["waypoints"], list) or len(value["waypoints"]) > 6:
        raise ValueError("Use at most six mandatory checkpoints")
    seen, ids = {start, goal}, set()
    for checkpoint in value["waypoints"]:
        exact(checkpoint, ("id", "cell", "tag"))
        key = identifier(checkpoint["id"])
        cell = _cell(checkpoint["cell"], width, height)
        if key in ids or cell in seen: raise ValueError("Duplicate checkpoint ID or cell")
        ids.add(key); seen.add(cell)
        if checkpoint["tag"] is not None: identifier(checkpoint["tag"])
    if not isinstance(value["blocked"], list) or len(value["blocked"]) > 142:
        raise ValueError("Too many blocked cells")
    blocked = [_cell(cell, width, height) for cell in value["blocked"]]
    if len(set(blocked)) != len(blocked) or seen & set(blocked):
        raise ValueError("Duplicate blocked cell or blocked route landmark")
    if not isinstance(value["route_cells"], list) or len(value["route_cells"]) != 2:
        raise ValueError("Declare minimum and maximum main-route cell counts")
    low = integer(value["route_cells"][0], 2, 64)
    high = integer(value["route_cells"][1], low, 64)
    exact(value["branches"], ("count", "length", "end_tag"))
    count = integer(value["branches"]["count"], 0, 4)
    length = integer(value["branches"]["length"], 1, 8)
    if high + count*length > 64:
        raise ValueError("Main route plus branches exceeds 64 modules")
    if value["branches"]["end_tag"] is not None: identifier(value["branches"]["end_tag"])
    integer(value["loops"], 0, 8); _tags(value["required_tags"])
    exact(value["player"], ("radius_m", "height_m", "margin_m"))
    number(value["player"]["radius_m"], .05, 1)
    number(value["player"]["height_m"], .2, 4)
    number(value["player"]["margin_m"], .01, .5)
    integer(value["search_budget"], 128, 50000)
    vector(value["anchor_m"], -1000, 1000)
    # Reuse Director's path rules instead of creating a second Unreal namespace.
    director_recipe({"kind": "architecture", "destination": value["destination"], "target_level": value["target_level"],
                     "anchor_m": [0,0,0], "yaw_deg": 0, "modules": {"Check": "/Game/Check.Check"},
                     "rows": [{"id":"Check","module":"Check","count":1,"origin_m":[0,0,0],"step_m":[0,0,0],"yaw_deg":0,"scale":[1,1,1]}]})
    return value


def catalog_specification(value):
    value = copy.deepcopy(value)
    exact(value, ("schema", "cell_m", "modules"))
    if value["schema"] != "cryptonyan.modular-catalog/1": raise ValueError("Unsupported module catalog")
    cell = number(value["cell_m"], 2, 50)
    if not isinstance(value["modules"], list) or not 1 <= len(value["modules"]) <= 32:
        raise ValueError("Use one to 32 module definitions")
    ids = set()
    for module in value["modules"]:
        exact(module, ("id", "preview_glb", "unreal_mesh", "tags", "doors", "blockers_m"))
        key = identifier(module["id"])
        if key.casefold() in ids: raise ValueError("Duplicate module ID")
        ids.add(key.casefold()); _tags(module["tags"])
        exact(module["preview_glb"], ("file", "sha256"))
        safe_path(Path.cwd(), module["preview_glb"]["file"]); _hash(module["preview_glb"]["sha256"])
        if module["unreal_mesh"] is not None: module["unreal_mesh"] = _object_path(module["unreal_mesh"])
        if not isinstance(module["doors"], list) or not 1 <= len(module["doors"]) <= 4:
            raise ValueError("Declare one to four centered cardinal doors")
        sides = set()
        for door in module["doors"]:
            exact(door, ("side", "kind", "width_m", "height_m"))
            if door["side"] not in SIDES or door["side"] in sides: raise ValueError("Duplicate or invalid door side")
            sides.add(door["side"]); identifier(door["kind"])
            number(door["width_m"], .1, cell); number(door["height_m"], .2, 10)
        if not isinstance(module["blockers_m"], list) or len(module["blockers_m"]) > 32:
            raise ValueError("Use at most 32 authored blocker boxes per module")
        for box in module["blockers_m"]:
            exact(box, ("min", "max")); vector(box["min"], -50, 50); vector(box["max"], -50, 50)
            if any(a >= b for a,b in zip(box["min"], box["max"])):
                raise ValueError("Blocker box has no volume")
            if any(abs(box[side][axis]) > cell/2+1e-6 for side in ("min","max") for axis in (0,1)):
                raise ValueError("Keep blocker proxies inside the module cell")
    return value


class _Budget:
    def __init__(self, limit): self.limit, self.used = limit, 0
    def step(self):
        self.used += 1
        if self.used > self.limit: raise ValueError("Search budget exhausted; change seed, constraints or modules")


def _draw(seed, *parts):
    return hashlib.sha256(json.dumps([seed,*parts],separators=(",", ":")).encode()).hexdigest()


def _neighbors(cell, spec):
    blocked = {tuple(c) for c in spec["blocked"]}
    for dx,dy in DELTAS:
        point = (cell[0]+dx,cell[1]+dy)
        if 0 <= point[0] < spec["grid"]["width"] and 0 <= point[1] < spec["grid"]["height"] and point not in blocked:
            yield point


def _main_route(spec, budget):
    targets = [tuple(w["cell"]) for w in spec["waypoints"]] + [tuple(spec["goal"])]
    low, high = spec["route_cells"]
    path, visited = [tuple(spec["start"])], {tuple(spec["start"])}
    def search(index):
        budget.step()
        current = path[-1]
        if current == targets[index]:
            index += 1
            if index == len(targets): return len(path) >= low
        if len(path) >= high: return False
        remaining = abs(current[0]-targets[index][0])+abs(current[1]-targets[index][1])
        remaining += sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a,b in zip(targets[index:],targets[index+1:]))
        if len(path)+remaining > high: return False
        choices = [c for c in _neighbors(current,spec) if c not in visited and c not in targets[index+1:]]
        choices.sort(key=lambda c:(abs(c[0]-targets[index][0])+abs(c[1]-targets[index][1]),_draw(spec["seed"],"route",len(path),c)))
        for cell in choices:
            path.append(cell); visited.add(cell)
            if search(index): return True
            visited.remove(cell); path.pop()
        return False
    if not search(0): raise ValueError("No main route found under these grid and route-length constraints")
    return path


def _edge(a,b): return tuple(sorted((a,b)))


def _reachable(start, goal, edges, removed=None):
    if start == removed or goal == removed: return False
    adjacency = {}
    for a,b in edges:
        if removed in (a,b): continue
        adjacency.setdefault(a,set()).add(b); adjacency.setdefault(b,set()).add(a)
    seen, stack = {start}, [start]
    while stack:
        node = stack.pop()
        if node == goal: return True
        for nxt in sorted(adjacency.get(node,set())-seen): seen.add(nxt); stack.append(nxt)
    return False


def _graph(spec,budget):
    route = _main_route(spec,budget)
    occupied, edges = set(route), {_edge(a,b) for a,b in zip(route,route[1:])}
    branches = []
    for index in range(spec["branches"]["count"]):
        found = None
        anchors = sorted(occupied,key=lambda c:_draw(spec["seed"],"branch",index,c))
        for anchor in anchors:
            extension = []
            def grow(current):
                budget.step()
                if len(extension) == spec["branches"]["length"]: return True
                choices = [c for c in _neighbors(current,spec) if c not in occupied and c not in extension]
                for nxt in sorted(choices,key=lambda c:_draw(spec["seed"],"grow",index,c,len(extension))):
                    extension.append(nxt)
                    if grow(nxt): return True
                    extension.pop()
                return False
            if grow(anchor): found = [anchor,*extension]; break
        if found is None: raise ValueError("Could not place the requested branches; change seed or free cells")
        branches.append(found)
        occupied.update(found); edges.update(_edge(a,b) for a,b in zip(found,found[1:]))
    candidates = {_edge(a,b) for a in occupied for b in _neighbors(a,spec) if b in occupied} - edges
    added = 0
    for edge in sorted(candidates,key=lambda e:_draw(spec["seed"],"loop",e)):
        if added == spec["loops"]: break
        trial = edges | {edge}
        # A checkpoint must be unavoidable, including after optional loops are inserted.
        if any(_reachable(tuple(spec["start"]),tuple(spec["goal"]),trial,tuple(w["cell"])) for w in spec["waypoints"]):
            continue
        edges.add(edge); added += 1
    if added != spec["loops"]: raise ValueError("Not enough loops preserve mandatory checkpoints; change constraints or seed")
    return route, branches, sorted(occupied), sorted(edges)


def _door_point(side, cell):
    dx,dy = DELTAS[SIDES.index(side)]
    return [dx*cell/2,dy*cell/2]


def _clear(module, player, cell):
    radius = player["radius_m"]+player["margin_m"]
    top = player["height_m"]+player["margin_m"]
    for door in module["doors"]:
        if door["width_m"] < 2*radius or door["height_m"] < top: return False
        point = _door_point(door["side"],cell)
        # Conservative swept square capsule footprint, center -> centered door.
        low = [min(0,p)-radius for p in point]
        high = [max(0,p)+radius for p in point]
        for box in module["blockers_m"]:
            if box["max"][2] <= 0 or box["min"][2] >= top: continue
            if all(min(high[i],box["max"][i])-max(low[i],box["min"][i]) > 1e-7 for i in (0,1)):
                return False
    return True


def _side(a,b):
    return SIDES[DELTAS.index((b[0]-a[0],b[1]-a[1]))]


def _assign(spec,catalog,cells,edges,branches,budget):
    adjacency = {c:set() for c in cells}
    for a,b in edges: adjacency[a].add(b); adjacency[b].add(a)
    tags = {c:set(spec["required_tags"]) for c in cells}
    for w in spec["waypoints"]:
        if w["tag"]: tags[tuple(w["cell"])].add(w["tag"])
    for branch in branches:
        if spec["branches"]["end_tag"]: tags[branch[-1]].add(spec["branches"]["end_tag"])
    candidates = {}
    for c in cells:
        wanted = {_side(c,n) for n in adjacency[c]}
        options = []
        for m in catalog["modules"]:
            if not tags[c] <= set(m["tags"]) or not _clear(m,spec["player"],catalog["cell_m"]): continue
            for rotation in range(4):
                doors = {SIDES[(SIDES.index(d["side"])+rotation)%4]:d for d in m["doors"]}
                if set(doors) == wanted: options.append({"module":m["id"],"yaw_deg":rotation*90,"doors":doors})
        candidates[c] = sorted(options,key=lambda o:_draw(spec["seed"],"module",c,o["module"],o["yaw_deg"]))
        if not options: raise ValueError("No module matches a cell's doors, tags and declared clearance")
    assigned = {}
    def compatible(c, option):
        return all(option["doors"][_side(c,n)]["kind"] == assigned[n]["doors"][_side(n,c)]["kind"] for n in adjacency[c] if n in assigned)
    def search():
        budget.step()
        if len(assigned) == len(cells): return True
        available = [(c,[o for o in candidates[c] if compatible(c,o)]) for c in cells if c not in assigned]
        c, options = min(available,key=lambda row:(len(row[1]),row[0]))
        for option in options:
            assigned[c] = option
            if search(): return True
            del assigned[c]
        return False
    if not search(): raise ValueError("Connector kinds cannot be matched within the generated topology")
    return assigned


def _binary_bounds(doc, binary):
    positions = {p["attributes"]["POSITION"] for p in doc["meshes"][0]["primitives"]}
    combined_low, combined_high = [math.inf]*3, [-math.inf]*3
    for index in positions:
        accessor = doc["accessors"][index]
        if accessor["componentType"] != 5126 or accessor["type"] != "VEC3" or accessor.get("normalized"):
            raise ValueError("Module positions require FLOAT VEC3 accessors")
        view = doc["bufferViews"][accessor["bufferView"]]
        stride = view.get("byteStride",12)
        if type(stride) is not int or not 12 <= stride <= 252 or stride%4:
            raise ValueError("Invalid position stride")
        offset = view.get("byteOffset",0)+accessor.get("byteOffset",0)
        end = offset+(accessor["count"]-1)*stride+12
        if offset < view.get("byteOffset",0) or end > view.get("byteOffset",0)+view["byteLength"] or end > len(binary):
            raise ValueError("Position data exceeds its binary view")
        low, high = [math.inf]*3, [-math.inf]*3
        for vertex in range(accessor["count"]):
            point = struct.unpack_from("<fff",binary,offset+vertex*stride)
            for axis,v in enumerate(point):
                number(v,-10000,10000)
                low[axis] = min(low[axis],v);high[axis] = max(high[axis],v)
        for field,actual in (("min",low),("max",high)):
            declared = accessor.get(field)
            if not isinstance(declared,list) or len(declared)!=3 or any(abs(a-number(b,-10000,10000))>1e-5 for a,b in zip(actual,declared)):
                raise ValueError("Accessor bounds disagree with actual binary vertex positions")
        combined_low = [min(a,b) for a,b in zip(combined_low,low)]
        combined_high = [max(a,b) for a,b in zip(combined_high,high)]
    return combined_low,combined_high


def _capture(recipe, catalog, source_root):
    spec, catalog = specification(recipe), catalog_specification(catalog)
    reports, payloads, total = {}, {}, 0
    for m in catalog["modules"]:
        path = safe_path(source_root,m["preview_glb"]["file"])
        if total + path.stat().st_size > MAX_SOURCES: raise ValueError("GLB batch exceeds 128 MiB")
        payload, report = inspect_source(path)
        if report["sha256"] != m["preview_glb"]["sha256"]: raise ValueError("Module GLB differs from pinned hash")
        doc,binary = glb.parse(payload)
        lo,hi = _binary_bounds(doc,binary)
        # Static glTF Y-up -> Unreal local X/Y/Z: [glTF X, glTF Z, glTF Y].
        bounds = [[lo[0],lo[2],lo[1]],[hi[0],hi[2],hi[1]]]
        half = catalog["cell_m"]/2
        if any(abs(corner[i]) > half+1e-5 for corner in bounds for i in (0,1)) or not bounds[0][2] <= 0 <= bounds[1][2]:
            raise ValueError("Module must fit its centered cell and include floor z=0 in its bounds")
        for door in m["doors"]:
            axis,sign = (0,1) if door["side"]=="east" else (0,-1) if door["side"]=="west" else (1,1) if door["side"]=="north" else (1,-1)
            if abs(bounds[1 if sign>0 else 0][axis]-sign*half) > .001:
                raise ValueError("Declared door edge does not meet the GLB cell boundary")
        filename = "sources/"+m["id"]+".glb"
        m["preview_glb"]["file"] = filename
        reports[m["id"]] = {**report,"bounds_unreal_m":bounds}
        payloads[filename] = payload; total += len(payload)
        if sum(r["vertices"] for r in reports.values()) > 2000000:
            raise ValueError("Module source batch exceeds two million vertices")
    budget = _Budget(spec["search_budget"])
    route,branches,cells,edges = _graph(spec,budget)
    chosen = _assign(spec,catalog,cells,edges,branches,budget)
    placements = []
    names = {c:"Tile_"+str(i).zfill(3) for i,c in enumerate(cells)}
    for c in cells:
        option = chosen[c]
        placements.append({"id":names[c],"cell":list(c),"module":option["module"],"yaw_deg":option["yaw_deg"],
                           "position_m":[spec["anchor_m"][0]+c[0]*catalog["cell_m"],spec["anchor_m"][1]+c[1]*catalog["cell_m"],spec["anchor_m"][2]]})
    if sum(reports[p["module"]]["triangles"] for p in placements) > 2000000:
        raise ValueError("Instanced preview exceeds two million triangles")
    links = [{"from":names[a],"to":names[b],"kind":chosen[a]["doors"][_side(a,b)]["kind"],
              "width_m":min(chosen[a]["doors"][_side(a,b)]["width_m"],chosen[b]["doors"][_side(b,a)]["width_m"]),
              "height_m":min(chosen[a]["doors"][_side(a,b)]["height_m"],chosen[b]["doors"][_side(b,a)]["height_m"])} for a,b in edges]
    value = {"schema":"cryptonyan.modular-plan/1","recipe":spec,"catalog":catalog,"modules":reports,"placements":placements,
             "links":links,"main_route":[names[c] for c in route],"branches":[[names[c] for c in b] for b in branches],
             "checkpoints":[{"id":w["id"],"tile":names[tuple(w["cell"])]} for w in spec["waypoints"]],
             "search_steps":budget.used,"engine_validated":False,"controller_validated":False,"navmesh_validated":False,
             "clearance_scope":"declared_centered_doors_and_authored_AABB_blocker_proxies"}
    value["identity"] = identity(value)
    qa = analyze(value)
    if not qa["model_passed"]: raise ValueError("Generated level failed graph or conservative geometry checks")
    return value,payloads


def make_plan(recipe,catalog,source_root):
    return _capture(recipe,catalog,Path(source_root).resolve())[0]


def placement_bounds(plan,placement):
    lo,hi = plan["modules"][placement["module"]]["bounds_unreal_m"]
    angle = math.radians(placement["yaw_deg"]); cs,sn = math.cos(angle),math.sin(angle)
    points = [[placement["position_m"][0]+x*cs-y*sn,placement["position_m"][1]+x*sn+y*cs,placement["position_m"][2]+z]
              for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])]
    return [[min(p[i] for p in points) for i in range(3)],[max(p[i] for p in points) for i in range(3)]]


def analyze(plan):
    if identity({k:v for k,v in plan.items() if k!="identity"}) != plan["identity"]: raise ValueError("Modular plan identity mismatch")
    by_id = {p["id"]:p for p in plan["placements"]}
    edges = {_edge(link["from"],link["to"]) for link in plan["links"]}
    start,goal = plan["main_route"][0],plan["main_route"][-1]
    mandatory = {w["id"]:not _reachable(start,goal,edges,w["tile"]) for w in plan["checkpoints"]}
    overlaps = []
    for i,a in enumerate(plan["placements"]):
        aa = placement_bounds(plan,a)
        for b in plan["placements"][i+1:]:
            bb = placement_bounds(plan,b)
            if all(min(aa[1][k],bb[1][k])-max(aa[0][k],bb[0][k]) > 1e-4 for k in range(3)):
                overlaps.append([a["id"],b["id"]])
    connected = all(_reachable(start,key,edges) for key in by_id)
    return {"schema":"cryptonyan.modular-analysis/1","plan_identity":plan["identity"],"model_passed":connected and all(mandatory.values()) and not overlaps,
            "connected":connected,"mandatory_checkpoints":mandatory,"overlapping_bounds":overlaps,
            "loop_count":len(edges)-len(by_id)+1,"clearance_scope":plan["clearance_scope"],"engine_validated":False,
            "controller_validated":False,"navmesh_validated":False}


def director(plan):
    modules = {m["id"]:m for m in plan["catalog"]["modules"]}
    used = sorted({p["module"] for p in plan["placements"]})
    if any(modules[key]["unreal_mesh"] is None for key in used): return None
    mapping = {key:"M"+str(i).zfill(2) for i,key in enumerate(used)}
    return director_recipe({"kind":"architecture","destination":plan["recipe"]["destination"],"target_level":plan["recipe"]["target_level"],
        "anchor_m":[0,0,0],"yaw_deg":0,"modules":{mapping[key]:modules[key]["unreal_mesh"] for key in used},
        "rows":[{"id":p["id"],"module":mapping[p["module"]],"count":1,"origin_m":p["position_m"],"step_m":[0,0,0],
                 "yaw_deg":p["yaw_deg"],"scale":[1,1,1]} for p in plan["placements"]]})


def points_csv(plan):
    out = io.StringIO(newline=""); writer = csv.writer(out,lineterminator="\n")
    writer.writerow(["id","module","x_cm","y_cm","z_cm","yaw_deg"])
    for p in plan["placements"]: writer.writerow([p["id"],p["module"],*[100*v for v in p["position_m"]],p["yaw_deg"]])
    return out.getvalue()


def overview_svg(plan):
    scale,pad = 70,35
    width,height = plan["recipe"]["grid"]["width"],plan["recipe"]["grid"]["height"]
    by_id = {p["id"]:p for p in plan["placements"]}
    def point(key):
        x,y = by_id[key]["cell"]; return pad+x*scale,pad+(height-1-y)*scale
    shapes = []
    for p in plan["placements"]:
        x,y = point(p["id"])
        shapes.append(f'<rect x="{x-26}" y="{y-26}" width="52" height="52" fill="#263b51" stroke="#6da3d3"/>')
    for link in plan["links"]:
        x,y = point(link["from"]);a,b = point(link["to"])
        shapes.append(f'<path d="M{x} {y} L{a} {b}" stroke="#a3d8ff" stroke-width="4"/>')
    for key,label in [(plan["main_route"][0],"START"),(plan["main_route"][-1],"GOAL")]+[(w["tile"],w["id"]) for w in plan["checkpoints"]]:
        x,y = point(key);shapes.append(f'<text x="{x}" y="{y-8}" fill="#ffdd83" text-anchor="middle">{html.escape(label)}</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width*scale}" height="{height*scale}" viewBox="0 0 {width*scale} {height*scale}"><title>Modular level — declared graph, not a navigation simulation</title>'+''.join(shapes)+'</svg>'


def prepare(recipe,catalog,source_root,output):
    root,output = Path(source_root).resolve(),Path(output).resolve(); _separate(root,output)
    plan,payloads = _capture(recipe,catalog,root)
    output.mkdir(parents=True,exist_ok=False)
    try:
        for name,data in payloads.items():
            path = safe_path(output,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        write_json(output/"plan.json",plan);write_json(output/"geometry.json",analyze(plan))
        (output/"level-points.csv").write_text(points_csv(plan),encoding="utf-8")
        (output/"overview.svg").write_text(overview_svg(plan),encoding="utf-8")
        if director(plan) is not None: write_json(output/"director.json",director(plan))
        if load_bundle(output) != plan: raise ValueError("Modular inputs changed during publication")
        return plan
    except BaseException:
        shutil.rmtree(output);raise


def load_bundle(folder):
    folder = Path(folder)
    if safe_path(folder,"plan.json").stat().st_size > 2*1024*1024: raise ValueError("Modular plan exceeds two MiB")
    value = read_json(safe_path(folder,"plan.json"))
    expected,_ = _capture(value["recipe"],value["catalog"],folder)
    if value != expected or read_json(safe_path(folder,"geometry.json")) != analyze(expected):
        raise ValueError("Modular plan, sources or geometry report changed")
    for name,text in (("level-points.csv",points_csv(expected)),("overview.svg",overview_svg(expected))):
        if safe_path(folder,name).read_text(encoding="utf-8") != text: raise ValueError("Modular derived artifact changed")
    unreal_recipe = director(expected)
    if unreal_recipe is not None and read_json(safe_path(folder,"director.json")) != unreal_recipe:
        raise ValueError("Director recipe differs from verified layout")
    return value


def preview(bundle,output,blender,timeout=180):
    number(timeout,1,600)
    bundle,output = Path(bundle).resolve(),Path(output).resolve();_separate(bundle,output)
    plan = load_bundle(bundle);binary = Path(blender).resolve(strict=True)
    if not binary.is_file():raise ValueError("Blender executable unavailable")
    output.mkdir(parents=True,exist_ok=False)
    receipt = {"schema":"cryptonyan.modular-preview/1","plan_identity":plan["identity"],"status":"running","engine_validated":False,"controller_validated":False}
    try:
        inputs = output/"inputs";inputs.mkdir()
        files = ["plan.json","geometry.json","level-points.csv","overview.svg"]+[m["preview_glb"]["file"] for m in plan["catalog"]["modules"]]
        if director(plan) is not None:files.append("director.json")
        for filename in files:
            dst=safe_path(inputs,filename);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(safe_path(bundle,filename),dst)
        if load_bundle(inputs)!=plan:raise ValueError("Modular inputs changed during snapshot")
        ctx=ExecutionContext(output,output,tuple(files),threading.Event(),time.monotonic()+timeout)
        run_process([str(binary),'--background','--factory-startup','--disable-autoexec','--threads','1','--python-exit-code','1',
                     '--python',str(Path(__file__).with_name('modular_worker.py')),'--',str(output)],ctx)
        if load_bundle(bundle)!=plan or load_bundle(inputs)!=plan:raise ValueError("Modular inputs changed during preview")
        report=read_json(safe_path(output,'preview-check.json'))
        if report['plan_identity']!=plan['identity'] or report['checked_placements']!=len(plan['placements']):raise ValueError("Incomplete modular preview check")
        number(report['max_bounds_error_m'],0,1e-4)
        receipt.update(status='preview_created_review_required',artifacts={name:{'sha256':digest(safe_path(output,name)),'bytes':safe_path(output,name).stat().st_size}
                       for name in ('modular-preview.blend','preview-check.json')})
        return receipt
    except BaseException:
        receipt['status']='failed';raise
    finally:write_json(output/'operation.json',receipt)


def example_recipe():
    return {"schema":"cryptonyan.modular-level/1","id":"TempleDemo","seed":42,"grid":{"width":5,"height":5},
        "start":[0,0],"goal":[4,0],"waypoints":[{"id":"Shrine","cell":[2,2],"tag":"Room"}],"blocked":[],
        "route_cells":[9,15],"branches":{"count":2,"length":2,"end_tag":"Reward"},"loops":0,"required_tags":["Walkable"],
        "player":{"radius_m":.35,"height_m":1.5,"margin_m":.15},"search_budget":20000,"anchor_m":[0,0,0],
        "destination":"/Game/CryptoNyan/DirectedReviews/ModularDemo","target_level":"/Game/CryptoNyan/ReviewMaps/ModularDemo"}


def demo(output,blender,timeout=120):
    number(timeout,1,600)
    output=Path(output).resolve();binary=Path(blender).resolve(strict=True)
    if not binary.is_file():raise ValueError("Blender executable unavailable")
    output.mkdir(parents=True,exist_ok=False)
    receipt={"schema":"cryptonyan.modular-demo/1","status":"running","engine_validated":False}
    try:
        ctx=ExecutionContext(output,output,(),threading.Event(),time.monotonic()+timeout)
        run_process([str(binary),'--background','--factory-startup','--disable-autoexec','--threads','1','--python-exit-code','1',
                     '--python',str(Path(__file__).with_name('modular_demo.py')),'--',str(output)],ctx)
        catalog=read_json(output/'catalog.json');recipe=read_json(output/'recipe.json')
        make_plan(recipe,catalog,output)
        names=['catalog.json','recipe.json']+[m['preview_glb']['file'] for m in catalog['modules']]
        receipt.update(status='sources_created_review_required',files={name:{'sha256':digest(safe_path(output,name)),'bytes':safe_path(output,name).stat().st_size} for name in names})
        return receipt
    except BaseException:
        receipt['status']='failed';raise
    finally:write_json(output/'operation.json',receipt)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('recipe',type=Path);prep.add_argument('--catalog',type=Path,required=True);prep.add_argument('--source-root',type=Path,required=True);prep.add_argument('--output',type=Path,required=True)
    demonstration=sub.add_parser('demo');demonstration.add_argument('--output',type=Path,required=True);demonstration.add_argument('--blender',type=Path,required=True)
    check=sub.add_parser('check');check.add_argument('bundle',type=Path)
    prev=sub.add_parser('preview');prev.add_argument('bundle',type=Path);prev.add_argument('--output',type=Path,required=True);prev.add_argument('--blender',type=Path,required=True)
    a=parser.parse_args(argv)
    if a.command=='demo':
        print(json.dumps(demo(a.output,a.blender),indent=2));return
    value=prepare(read_json(a.recipe),read_json(a.catalog),a.source_root,a.output) if a.command=='prepare' else load_bundle(a.bundle) if a.command=='check' else preview(a.bundle,a.output,a.blender)
    print(json.dumps(value,indent=2))


if __name__=='__main__':main()
