# SPDX-License-Identifier: GPL-3.0-or-later
"""Verified Image Workshop snapshots, explicit selection and copy-only restoration."""
import argparse
import base64
from contextlib import closing
import html
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from loopcut import glb
from .animation_doctor import exact, read_json
from .creative_director import integer
from .image_workshop import identity, load_bundle
from .materials import read_png
from .reference_board import identifier, text, _separate
from .storage import OwnerLock, digest, safe_path, write_json

SCHEMA = "cryptonyan.visual-versions/1"
ARTIFACTS = ("candidate.blend", "candidate.glb", "render.png", "geometry.json", "asset-doctor.json", "comparison.html")
MAX_ATTEMPT = 512 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_VERSIONS = 32


def _json(folder, filename):
    path = safe_path(folder, filename)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Metadata exceeds 1 MiB")
    return read_json(path)


def inspect_attempt(folder):
    """Check receipt, frozen inputs and GLB/report agreement; never open the blend."""
    folder = Path(folder)
    receipt = _json(folder, "operation.json")
    exact(receipt, ("schema", "plan_identity", "status", "artifacts", "visual_quality_validated", "engine_validated"))
    if (receipt["schema"] != "cryptonyan.image-attempt/1" or
            receipt["status"] != "candidate_created_review_required" or
            receipt["visual_quality_validated"] is not False or receipt["engine_validated"] is not False or
            not isinstance(receipt["artifacts"], dict) or set(receipt["artifacts"]) != set(ARTIFACTS)):
        raise ValueError("Require a completed, review-required Image Workshop attempt")
    plan = load_bundle(safe_path(folder, "inputs"))
    if receipt["plan_identity"] != plan["identity"]:
        raise ValueError("Attempt plan identity mismatch")
    names = list(ARTIFACTS) + ["operation.json", "inputs/plan.json", "inputs/reference.png"]
    names += ["inputs/" + source["file"] for source in plan["sources"].values()]
    inventory, total = {}, 0
    for filename in names:
        path = safe_path(folder, filename)
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_ATTEMPT:
            raise ValueError("Invalid or oversized attempt file")
        total += path.stat().st_size
        if total > MAX_ATTEMPT:
            raise ValueError("Attempt exceeds archive budget")
        record = {"sha256": digest(path), "bytes": path.stat().st_size}
        if filename in ARTIFACTS and receipt["artifacts"][filename] != record:
            raise ValueError("Attempt artifact changed: " + filename)
        inventory[filename] = record
    _, size = read_png(safe_path(folder, "render.png"))
    if [size["width"], size["height"]] != plan["recipe"]["camera"]["resolution"]:
        raise ValueError("Render resolution mismatch")
    report = _json(folder, "geometry.json")
    integer(report["triangles"], 0, plan["recipe"]["triangle_budget"])
    if report["plan_identity"] != plan["identity"]:
        raise ValueError("Geometry plan mismatch")
    if inventory["candidate.glb"]["bytes"] > 128 * 1024 * 1024:
        raise ValueError("GLB exceeds export budget")
    doc, binary = glb.parse(safe_path(folder, "candidate.glb").read_bytes())
    summary = glb.summary(doc)
    if glb.validate(doc, binary) or glb.compare(summary, report["objects"]) or summary["tris"] != report["triangles"]:
        raise ValueError("GLB and geometry report disagree")
    return {"plan": plan, "files": inventory, "bytes": total, "triangles": report["triangles"]}


def create(folder, asset_id, title, project=None):
    identifier(asset_id); text(title)
    folder = Path(folder).resolve()
    project_root = None
    if project is not None:
        from .game_project import GameProject
        game = GameProject(project)
        project_root = str(game.root)
        _separate(folder, game.root)
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "versions").mkdir()
    value = {"schema": SCHEMA, "id": asset_id, "title": title, "project_root": project_root,
             "revision": 0, "selected": None, "versions": []}
    write_json(folder / "history.json", value)
    return value


def load(folder):
    folder = Path(folder).resolve()
    value = _json(folder, "history.json")
    exact(value, ("schema", "id", "title", "project_root", "revision", "selected", "versions"))
    if value["schema"] != SCHEMA:
        raise ValueError("Unsupported history")
    identifier(value["id"]); text(value["title"]); integer(value["revision"], 0, 1000000)
    if value["project_root"] is not None:
        if not isinstance(value["project_root"], str) or not Path(value["project_root"]).is_absolute():
            raise ValueError("Invalid project boundary")
        _separate(folder, Path(value["project_root"]))
    if not isinstance(value["versions"], list) or len(value["versions"]) > MAX_VERSIONS:
        raise ValueError("Too many versions")
    ids, total = set(), 0
    for item in value["versions"]:
        exact(item, ("id", "label", "snapshot_identity", "bytes"))
        identifier(item["id"]); text(item["label"])
        if item["id"] in ids:
            raise ValueError("Duplicate version")
        ids.add(item["id"])
        from .unreal_material_variants import _hash
        _hash(item["snapshot_identity"])
        integer(item["bytes"], 1, MAX_ATTEMPT)
        total += item["bytes"]
    if total > MAX_TOTAL or (value["selected"] is not None and value["selected"] not in ids):
        raise ValueError("Invalid selection or archive budget")
    return value


def _revision(value, revision):
    integer(revision, 0, 1000000)
    if revision != value["revision"]:
        raise ValueError("History changed; reload before editing")


def _destination(folder, value, destination):
    destination = Path(destination).resolve()
    _separate(Path(folder), destination)
    if value["project_root"]:
        _separate(Path(value["project_root"]), destination)
    return destination


def _copy(source, output, files):
    for filename in files:
        src = safe_path(source, filename)
        dst = safe_path(output, filename)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with src.open("rb") as inp, dst.open("xb") as out:
            remaining = files[filename]["bytes"]
            while remaining:
                chunk = inp.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise ValueError("Source shrank during copy")
                out.write(chunk)
                remaining -= len(chunk)
            if inp.read(1):
                raise ValueError("Source grew during copy")


def archive(folder, revision, version_id, attempt, label, board_folder=None, reference_id=None):
    identifier(version_id); text(label)
    folder, attempt = Path(folder).resolve(), Path(attempt).resolve()
    _separate(folder, attempt)
    with closing(OwnerLock(safe_path(folder, "edit.lock"))):
        history = load(folder); _revision(history, revision)
        if len(history["versions"]) >= MAX_VERSIONS or any(v["id"] == version_id for v in history["versions"]):
            raise ValueError("Duplicate version or history full")
        found = inspect_attempt(attempt)
        provenance = None
        if board_folder is not None:
            from . import reference_board as boards
            context = boards.context(board_folder)
            ref = next((r for r in context["board"]["references"] if r["id"] == reference_id), None)
            if (ref is None or ref["image"]["sha256"] != found["plan"]["reference"]["sha256"] or
                    ref["recipe"] != found["plan"]["recipe"] or
                    context["targets"][reference_id] not in ("unchanged", "not_linked")):
                raise ValueError("Board reference, recipe or target differs from candidate")
            project = context["board"]["project"]
            if project and history["project_root"] != project["root"]:
                raise ValueError("Create history with the board's project boundary")
            provenance = {"board_identity": context["board_identity"], "board_id": context["board"]["id"],
                          "revision": context["board"]["revision"], "reference": ref, "project": project}
        elif reference_id is not None:
            raise ValueError("Reference requires a board")
        if sum(v["bytes"] for v in history["versions"]) + found["bytes"] > MAX_TOTAL:
            raise ValueError("History exceeds storage budget")
        snapshot = {"schema": "cryptonyan.visual-snapshot/1", "attempt": found, "board": provenance}
        entry = {"id": version_id, "label": label, "snapshot_identity": identity(snapshot), "bytes": found["bytes"]}
        versions = safe_path(folder, "versions")
        destination = safe_path(versions, version_id)
        if destination.exists():
            raise ValueError("Version directory already exists (possibly an interrupted archive)")
        with tempfile.TemporaryDirectory(prefix=".pending-", dir=versions) as temp:
            staged = Path(temp) / "snapshot"
            staged.mkdir()
            _copy(attempt, staged, found["files"])
            if inspect_attempt(staged) != found:
                raise ValueError("Attempt changed during snapshot")
            write_json(staged / "snapshot.json", snapshot)
            staged.rename(destination)
        # Index is the commit point. Interrupted unpublished directories are never listed.
        history["versions"].append(entry)
        history["revision"] += 1
        write_json(folder / "history.json", history)
        return history


def read_version(folder, version_id):
    identifier(version_id)
    history = load(folder)
    entry = next((v for v in history["versions"] if v["id"] == version_id), None)
    if entry is None:
        raise ValueError("Unknown archived version")
    path = safe_path(folder, "versions/" + version_id)
    snapshot = _json(path, "snapshot.json")
    exact(snapshot, ("schema", "attempt", "board"))
    if snapshot["schema"] != "cryptonyan.visual-snapshot/1" or identity(snapshot) != entry["snapshot_identity"]:
        raise ValueError("Snapshot identity mismatch")
    found = inspect_attempt(path)
    if found != snapshot["attempt"] or found["bytes"] != entry["bytes"]:
        raise ValueError("Archived files changed")
    return snapshot


def select(folder, revision, version_id):
    with closing(OwnerLock(safe_path(folder, "edit.lock"))):
        history = load(folder); _revision(history, revision)
        read_version(folder, version_id)
        history["selected"] = version_id
        history["revision"] += 1
        write_json(Path(folder) / "history.json", history)
        return history


def restore(folder, version_id, output):
    history = load(folder)
    output = _destination(folder, history, output)
    snapshot = read_version(folder, version_id)
    output.mkdir(parents=True, exist_ok=False)
    try:
        source = safe_path(folder, "versions/" + version_id)
        _copy(source, output, snapshot["attempt"]["files"])
        if inspect_attempt(output) != snapshot["attempt"]:
            raise ValueError("Snapshot changed during restoration")
        receipt = {"schema": "cryptonyan.visual-restore/1", "version": version_id,
                   "snapshot_identity": identity(snapshot), "board": snapshot["board"],
                   "scene_opened": False, "game_modified": False}
        write_json(output / "restore.json", receipt)
        return receipt
    except BaseException:
        shutil.rmtree(output)
        raise


def compare(folder, left, right, output):
    history = load(folder)
    output = _destination(folder, history, output)
    a, b = read_version(folder, left), read_version(folder, right)
    pa, pb = a["attempt"]["plan"], b["attempt"]["plan"]
    result = {"schema": "cryptonyan.visual-comparison/1", "left": left, "right": right,
              "same_reference": pa["reference"] == pb["reference"],
              "same_camera": pa["recipe"]["camera"] == pb["recipe"]["camera"],
              "triangles": [a["attempt"]["triangles"], b["attempt"]["triangles"]],
              "changed_recipe_fields": [key for key in pa["recipe"] if pa["recipe"][key] != pb["recipe"][key]],
              "visual_quality_validated": False, "engine_validated": False}
    figures = []
    for key, snapshot in ((left, a), (right, b)):
        source = safe_path(folder, "versions/" + key)
        images = []
        for filename in ("inputs/reference.png", "render.png"):
            image, _ = read_png(safe_path(source, filename))
            if hashlib.sha256(image).hexdigest() != snapshot["attempt"]["files"][filename]["sha256"]:
                raise ValueError("Comparison image changed")
            images.append('<img alt="' + filename + '" src="data:image/png;base64,' + base64.b64encode(image).decode() + '">')
        figures.append('<section><h2>' + html.escape(key) + '</h2>' + ''.join(images) + '<pre>' +
                       html.escape(json.dumps(snapshot["attempt"]["plan"]["recipe"], ensure_ascii=False, indent=2)) + '</pre></section>')
    content = ('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Versions visuelles</title>'
               '<style>body{font:16px sans-serif;margin:2rem}main{display:flex;gap:2rem}section{width:48%}'
               'img{width:48%}pre{white-space:pre-wrap}</style><h1>Comparaison de candidats</h1>'
               '<p>Référence puis rendu pour chaque version. Vérifier silhouette, proportions et détails. '
               'Aucun score artistique ; aucune validation Unreal.</p><pre>' +
               html.escape(json.dumps(result, ensure_ascii=False, indent=2)) + '</pre>' +
               ('<p>Attention : référence ou caméra différente ; comparaison visuelle non équivalente.</p>'
                if not result["same_reference"] or not result["same_camera"] else '') +
               '<main>' + ''.join(figures) + '</main></html>')
    with output.open("x", encoding="utf-8") as stream:
        stream.write(content)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "list", "archive", "select", "restore", "compare", "check"):
        p = sub.add_parser(command); p.add_argument("folder", type=Path)
        if command == "create":
            p.add_argument("--id", required=True); p.add_argument("--title", required=True); p.add_argument("--project", type=Path)
        if command in ("archive", "select"):
            p.add_argument("--revision", type=int, required=True)
        if command in ("archive", "select", "restore", "check"):
            p.add_argument("--version", required=True)
        if command == "archive":
            p.add_argument("--attempt", type=Path, required=True); p.add_argument("--label", required=True)
            p.add_argument("--board", type=Path); p.add_argument("--reference")
        if command in ("restore", "compare"):
            p.add_argument("--output", type=Path, required=True)
        if command == "compare":
            p.add_argument("--left", required=True); p.add_argument("--right", required=True)
    a = parser.parse_args(argv)
    if a.command == "create": result = create(a.folder, a.id, a.title, a.project)
    elif a.command == "list": result = load(a.folder)
    elif a.command == "archive": result = archive(a.folder, a.revision, a.version, a.attempt, a.label, a.board, a.reference)
    elif a.command == "select": result = select(a.folder, a.revision, a.version)
    elif a.command == "restore": result = restore(a.folder, a.version, a.output)
    elif a.command == "compare": result = compare(a.folder, a.left, a.right, a.output)
    else: result = read_version(a.folder, a.version)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
