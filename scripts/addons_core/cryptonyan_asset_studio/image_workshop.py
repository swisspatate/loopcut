# SPDX-License-Identifier: GPL-3.0-or-later
"""Reference-driven 3D candidates: explicit agent recipes, isolated Blender, review.

No vision inference or provider submission is performed by this module. An agent
interprets the image and supplies the recipe; local GLBs can come from any provider.
"""
import argparse
import base64
import copy
import hashlib
import html
import json
from pathlib import Path
import threading
import time

from loopcut import glb
from .animation_doctor import exact, name, number, read_json
from .creative_director import identifier, integer, rows, vector
from .executors import ExecutionContext, run_process
from .materials import read_png
from .publication import MAX_GLB_BYTES, texture_inventory
from .storage import digest, safe_path, write_json

SCHEMA = "cryptonyan.image-workshop/1"
MAX_GLB = 32 * 1024 * 1024


def budgets(recipe, sources):
    triangles, vertices, pixels = 0, 0, 0
    for part in recipe["parts"]:
        if part["shape"] == "glb":
            source = sources[part["source"]]
            triangles += source["triangles"]
            vertices += source["vertices"]
            pixels += sum(t["width"]*t["height"] for t in source["textures"])
        else:
            count, verts = {"box": (12, 8), "cylinder": (124, 64), "cone": (62, 33)}[part["shape"]]
            triangles += count; vertices += verts
    if triangles > recipe["triangle_budget"] or vertices > 600000 or pixels > 32*1024*1024:
        raise ValueError("Recipe exceeds geometry or decoded texture budget")
    return triangles


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def specification(value):
    value = copy.deepcopy(value)
    exact(value, ("schema", "id", "intent", "assumptions", "triangle_budget", "camera", "parts", "sources"))
    if value["schema"] != SCHEMA:
        raise ValueError("Unsupported image workshop schema")
    identifier(value["id"]); name(value["intent"])
    for text in rows(value["assumptions"], 16):
        name(text)
    integer(value["triangle_budget"], 12, 200000)
    camera = value["camera"]
    exact(camera, ("position_m", "target_m", "projection", "lens_mm", "ortho_scale_m", "resolution", "samples"))
    a, b = vector(camera["position_m"], -1000, 1000), vector(camera["target_m"], -1000, 1000)
    if sum((x-y)**2 for x, y in zip(a, b)) < .0001 or camera["projection"] not in ("PERSP", "ORTHO"):
        raise ValueError("Invalid camera")
    number(camera["lens_mm"], 10, 200); number(camera["ortho_scale_m"], .1, 1000)
    if not isinstance(camera["resolution"], list) or len(camera["resolution"]) != 2:
        raise ValueError("Expected render width and height")
    for n in camera["resolution"]:
        integer(n, 32, 1024)
    integer(camera["samples"], 1, 64)
    sources = value["sources"]
    if not isinstance(sources, dict) or len(sources) > 8:
        raise ValueError("Use at most eight local GLBs")
    for key, source in sources.items():
        identifier(key)
        exact(source, ("file", "provider", "model", "license", "reference_sha256"))
        safe_path(Path.cwd(), source["file"])
        if Path(source["file"]).suffix.lower() != ".glb":
            raise ValueError("Source must be a local GLB")
        for field in ("provider", "model", "license"):
            name(source[field])
        from .unreal_material_variants import _hash
        _hash(source["reference_sha256"])
    used, ids = set(), set()
    for part in rows(value["parts"], 64):
        exact(part, ("id", "shape", "position_m", "size_m", "yaw_deg", "color"), ("source",))
        key = identifier(part["id"])
        if key.casefold() in ids or part["shape"] not in ("box", "cylinder", "cone", "glb"):
            raise ValueError("Duplicate part or unsupported geometry")
        ids.add(key.casefold())
        vector(part["position_m"], -500, 500); vector(part["size_m"], .001, 500)
        vector(part["color"], 0, 1); number(part["yaw_deg"], -360, 360)
        if part["shape"] == "glb":
            if part.get("source") not in sources:
                raise ValueError("Unknown GLB source")
            used.add(part["source"])
        elif "source" in part:
            raise ValueError("Only GLB parts can have a source")
    if used != set(sources):
        raise ValueError("Unused GLB sources")
    return value


def inspect_source(path):
    """Narrow local handoff: one static mesh/node, embedded standard PBR only.

    Deliberately rejects complex provider scenes instead of silently dropping rigs,
    hierarchy, extensions, transforms, external textures or unsupported channels.
    """
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 20 <= path.stat().st_size <= MAX_GLB:
        raise ValueError("Expected bounded local GLB")
    payload = path.read_bytes()
    if len(payload) > MAX_GLB:
        raise ValueError("GLB exceeds budget")
    try:
        doc, binary = glb.parse(payload)
        if glb.validate(doc, binary):
            raise ValueError("GLB failed Loopcut validation")
        nodes = doc.get("nodes", [])
        if (len(nodes) != 1 or nodes[0].get("mesh") != 0 or
                any(k in nodes[0] for k in ("children", "skin", "matrix", "translation", "rotation", "scale")) or
                len(doc.get("meshes", [])) != 1 or len(doc.get("materials", [])) != 1 or
                doc.get("skins") or doc.get("animations") or doc.get("cameras") or
                doc.get("extensionsUsed") or doc.get("extensionsRequired") or
                any("uri" in b for b in doc.get("buffers", []))):
            raise ValueError("Use one static mesh with baked transforms and one material")
        # Reject nested extensions/URIs too, even if their root declaration is absent.
        def walk(item):
            if isinstance(item, dict):
                if item.get("extensions") or "uri" in item:
                    raise ValueError("External resources or extensions are unsupported")
                for child in item.values():
                    walk(child)
            elif isinstance(item, list):
                for child in item:
                    walk(child)
        walk(doc)
        for acc in doc.get("accessors", []):
            integer(acc["count"], 1, 600000)
            if acc.get("sparse"):
                raise ValueError("Sparse accessors are unsupported")
        vertices = 0
        for primitive in rows(doc["meshes"][0]["primitives"], 16):
            if primitive.get("mode", 4) != 4 or primitive.get("targets") or primitive.get("material") != 0:
                raise ValueError("Require static triangles with material zero")
            vertices += doc["accessors"][primitive["attributes"]["POSITION"]]["count"]
        integer(vertices, 1, 600000)
        textures = texture_inventory(doc, binary)
        # The untextured path also has to use a supported opaque PBR material.
        mat = doc["materials"][0]
        if mat.get("alphaMode", "OPAQUE") != "OPAQUE" or mat.get("emissiveTexture") or mat.get("occlusionTexture"):
            raise ValueError("Unsupported material")
        found = glb.summary(doc)
        integer(found["tris"], 1, 200000)
        if found["warnings"]:
            raise ValueError("Unsupported GLB primitive")
    except (KeyError, TypeError, IndexError, AttributeError, RecursionError, OverflowError) as exc:
        raise ValueError("Malformed static GLB") from exc
    return payload, {"sha256": hashlib.sha256(payload).hexdigest(), "triangles": found["tris"],
                     "vertices": vertices, "textures": textures}


def prepare(reference, recipe, output, source_root=None):
    recipe = specification(recipe)
    reference = Path(reference)
    if reference.is_symlink():
        raise ValueError("Reference must be a regular PNG")
    image, dimensions = read_png(reference)
    sha = hashlib.sha256(image).hexdigest()
    root = Path(source_root or reference.parent).resolve()
    sources, payloads = {}, {}
    for key, source in recipe["sources"].items():
        if source["reference_sha256"] != sha:
            raise ValueError("GLB provenance refers to a different reference")
        data, report = inspect_source(safe_path(root, source["file"]))
        if sum(len(p) for p in payloads.values()) + len(data) > MAX_GLB_BYTES:
            raise ValueError("Source batch exceeds 128 MiB")
        filename = "source_"+key+".glb"
        sources[key] = {**report, "file": filename}
        payloads[filename] = data
    estimate = budgets(recipe, sources)
    manifest = {"schema": "cryptonyan.reference-bundle/1", "recipe": recipe,
                "reference": {"file": "reference.png", "sha256": sha, **dimensions},
                "sources": sources, "estimated_triangles": estimate}
    manifest["identity"] = identity(manifest)
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output / "reference.png").write_bytes(image)
    for filename, data in payloads.items():
        (output / filename).write_bytes(data)
    write_json(output / "plan.json", manifest)
    return manifest


def load_bundle(folder):
    folder = Path(folder)
    data = read_json(safe_path(folder, "plan.json"))
    exact(data, ("schema", "recipe", "reference", "sources", "estimated_triangles", "identity"))
    if data["schema"] != "cryptonyan.reference-bundle/1" or identity({k: v for k, v in data.items() if k != "identity"}) != data["identity"]:
        raise ValueError("Reference bundle identity mismatch")
    recipe = specification(data["recipe"])
    ref = data["reference"]
    image, dimensions = read_png(safe_path(folder, "reference.png"))
    if ref != {"file": "reference.png", "sha256": hashlib.sha256(image).hexdigest(), **dimensions}:
        raise ValueError("Reference changed")
    if set(data["sources"]) != set(recipe["sources"]):
        raise ValueError("Source inventory mismatch")
    for key, source in data["sources"].items():
        _, report = inspect_source(safe_path(folder, "source_"+key+".glb"))
        if source != {**report, "file": "source_"+key+".glb"} or recipe["sources"][key]["reference_sha256"] != ref["sha256"]:
            raise ValueError("Source changed")
    if sum(safe_path(folder, s["file"]).stat().st_size for s in data["sources"].values()) > MAX_GLB_BYTES:
        raise ValueError("Source batch exceeds 128 MiB")
    if budgets(recipe, data["sources"]) != data["estimated_triangles"]:
        raise ValueError("Triangle budget mismatch")
    return data


def comparison_html(reference, render, recipe):
    # Self-contained review; no guessed score and no external URLs/scripts.
    images = [base64.b64encode(read_png(Path(p))[0]).decode("ascii") for p in (reference, render)]
    notes = "".join("<li>"+html.escape(s)+"</li>" for s in recipe["assumptions"])
    return ('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Image vers 3D</title>'
            '<style>body{font:16px system-ui;max-width:1200px;margin:2rem auto;padding:1rem;background:#161922;color:#eee}'
            '.pair{display:flex;gap:1rem}.pair figure{flex:1;margin:0}img{width:100%;height:auto}li{margin:.5rem}</style>'
            '<h1>'+html.escape(recipe["intent"])+'</h1><div class="pair">'+
            ''.join('<figure><img alt="'+label+'" src="data:image/png;base64,'+im+'"><figcaption>'+label+'</figcaption></figure>'
                    for label, im in zip(("Référence", "Candidat Blender"), images))+
            '</div><h2>Hypothèses de reconstruction</h2><ul>'+notes+'</ul>'
            '<p>Comparer silhouette, proportions, détails et caméra. Aucun score de fidélité automatique. '
            'Les parties cachées sont interprétées. Ce rendu ne valide ni collisions, ni performances, ni Unreal.</p></html>')


def run(bundle, output, blender, timeout=180):
    number(timeout, 1, 600)
    bundle, output, binary = Path(bundle).resolve(), Path(output).resolve(), Path(blender).resolve()
    plan = load_bundle(bundle)
    if not binary.is_file():
        raise ValueError("Blender executable unavailable")
    if output.is_relative_to(bundle):
        raise ValueError("Keep attempts outside the immutable reference bundle")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    # Snapshot verified bytes; never pass a live game scene or original image to Blender.
    files = ["plan.json", "reference.png"]+[s["file"] for s in plan["sources"].values()]
    inputs = output / "inputs"; inputs.mkdir()
    for filename in files:
        (inputs / filename).write_bytes(safe_path(bundle, filename).read_bytes())
    if load_bundle(inputs) != plan:
        raise ValueError("Inputs changed during snapshot")
    receipt = {"schema": "cryptonyan.image-attempt/1", "plan_identity": plan["identity"],
               "status": "running", "artifacts": {}, "visual_quality_validated": False, "engine_validated": False}
    write_json(output / "operation.json", receipt)
    try:
        ctx = ExecutionContext(output, output, tuple(files), threading.Event(), time.monotonic()+timeout)
        run_process([str(binary), "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                     "--python-exit-code", "1", "--python", str(Path(__file__).with_name("image_worker.py")),
                     "--", str(output)], ctx)
        if load_bundle(bundle) != plan or load_bundle(inputs) != plan:
            raise ValueError("Inputs changed during build")
        report = read_json(safe_path(output, "geometry.json"))
        if report["plan_identity"] != plan["identity"] or report["triangles"] > plan["recipe"]["triangle_budget"]:
            raise ValueError("Invalid geometry report")
        _, render_size = read_png(safe_path(output, "render.png"))
        if [render_size["width"], render_size["height"]] != plan["recipe"]["camera"]["resolution"]:
            raise ValueError("Render resolution mismatch")
        if safe_path(output, "candidate.glb").stat().st_size > MAX_GLB_BYTES:
            raise ValueError("Export exceeds 128 MiB")
        doc, binary_data = glb.parse(safe_path(output, "candidate.glb").read_bytes())
        if glb.validate(doc, binary_data) or glb.compare(glb.summary(doc), report["objects"]):
            raise ValueError("Export differs from Blender geometry")
        (output / "comparison.html").write_text(comparison_html(inputs / "reference.png", output / "render.png", plan["recipe"]), encoding="utf-8")
        for filename in ("candidate.blend", "candidate.glb", "render.png", "geometry.json", "asset-doctor.json", "comparison.html"):
            path = safe_path(output, filename)
            receipt["artifacts"][filename] = {"sha256": digest(path), "bytes": path.stat().st_size}
        receipt["status"] = "candidate_created_review_required"
        return receipt
    except BaseException:
        receipt["status"] = "failed"
        raise
    finally:
        write_json(output / "operation.json", receipt)


def main(argv=None):
    p = argparse.ArgumentParser(description="Build an image-guided Blender candidate from an explicit agent recipe")
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("reference", type=Path); prep.add_argument("recipe", type=Path)
    prep.add_argument("--source-root", type=Path); prep.add_argument("--output", type=Path, required=True)
    build = sub.add_parser("build")
    build.add_argument("bundle", type=Path); build.add_argument("--blender", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True); build.add_argument("--timeout", type=float, default=180)
    check = sub.add_parser("check"); check.add_argument("bundle", type=Path)
    source = sub.add_parser("inspect-glb", help="Check a local TRELLIS/other provider output before preparing a bundle")
    source.add_argument("glb", type=Path)
    args = p.parse_args(argv)
    result = (prepare(args.reference, read_json(args.recipe), args.output, args.source_root) if args.command == "prepare" else
              run(args.bundle, args.output, args.blender, args.timeout) if args.command == "build" else
              inspect_source(args.glb)[1] if args.command == "inspect-glb" else load_bundle(args.bundle))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
