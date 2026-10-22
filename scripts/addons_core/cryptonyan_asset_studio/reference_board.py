# SPDX-License-Identifier: GPL-3.0-or-later
"""Local reference boards: immutable PNG snapshots, annotations and explicit recipes.

No image inference, scene edits or generation on import/read. Mutations use one
short-lived owner lock and an expected revision to reject stale editor updates.
"""
import argparse
import base64
import copy
from contextlib import closing
import hashlib
import html
import json
from pathlib import Path
import re

from .animation_doctor import exact, number
from .creative_director import integer
from .image_workshop import identity, specification, prepare
from .materials import read_png
from .storage import OwnerLock, digest, safe_path, write_json

SCHEMA = "cryptonyan.reference-board/1"
MAX_IMAGE = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", value):
        raise ValueError("Use a 1-40 character lowercase identifier")
    return value


def text(value, limit=2048, *, empty=True):
    if (not isinstance(value, str) or len(value) > limit or (not empty and not value.strip())
            or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise ValueError("Invalid or oversized reference text")
    return value


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Invalid reference hash")


def annotations(value):
    if not isinstance(value, list) or len(value) > 16:
        raise ValueError("Use at most sixteen annotations per reference")
    seen = set()
    for item in value:
        exact(item, ("id", "text", "rect"))
        key = identifier(item["id"])
        if key in seen:
            raise ValueError("Duplicate annotation identifier")
        seen.add(key)
        text(item["text"], 512, empty=False)
        rect = item["rect"]
        if not isinstance(rect, list) or len(rect) != 4:
            raise ValueError("Rectangle must be [x, y, width, height] from the top-left")
        x, y, w, h = [number(n, 0, 1) for n in rect]
        if w <= 0 or h <= 0 or x + w > 1 or y + h > 1:
            raise ValueError("Annotation rectangle must fit inside the image")
    return copy.deepcopy(value)


def _png(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_IMAGE:
        raise ValueError("Select a regular RGB/RGBA PNG up to 8 MiB")
    data, dimensions = read_png(path)
    if len(data) > MAX_IMAGE:
        raise ValueError("Reference image exceeds 8 MiB")
    return data, {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), **dimensions}


def _separate(a, b):
    a, b = Path(a).resolve(), Path(b).resolve()
    if a.is_relative_to(b) or b.is_relative_to(a):
        raise ValueError("Board, output and game project directories must remain separate")


def create(folder, board_id, title, project=None):
    identifier(board_id); text(title, 128, empty=False)
    folder = Path(folder).absolute()
    project_info = None
    if project:
        from .game_project import GameProject
        game = GameProject(project)
        _separate(folder, game.root)
        project_info = {"root": str(game.root), "identity": game._project_identity()}
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "images").mkdir()
    board = {"schema": SCHEMA, "id": board_id, "title": title, "revision": 0,
             "project": project_info, "references": []}
    write_json(folder / "board.json", board)
    return board


def load(folder):
    folder = Path(folder)
    path = safe_path(folder, "board.json")
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Board metadata exceeds 1 MiB")
    value = json.loads(path.read_text(encoding="utf-8"))
    exact(value, ("schema", "id", "title", "revision", "project", "references"))
    if value["schema"] != SCHEMA:
        raise ValueError("Unsupported reference board schema")
    identifier(value["id"]); text(value["title"], 128, empty=False)
    integer(value["revision"], 0, 1000000)
    if value["project"] is not None:
        exact(value["project"], ("root", "identity"))
        if not isinstance(value["project"]["root"], str) or not Path(value["project"]["root"]).is_absolute():
            raise ValueError("Project root must be an absolute local path")
        _hash(value["project"]["identity"])
        _separate(folder, value["project"]["root"])
    refs = value["references"]
    if not isinstance(refs, list) or len(refs) > 16:
        raise ValueError("Use at most sixteen references per board")
    seen, total, pixels = set(), 0, 0
    for ref in refs:
        exact(ref, ("id", "title", "notes", "image", "annotations", "target", "recipe"))
        key = identifier(ref["id"])
        if key in seen:
            raise ValueError("Duplicate reference identifier")
        seen.add(key)
        text(ref["title"], 128, empty=False); text(ref["notes"])
        annotations(ref["annotations"])
        image = ref["image"]
        exact(image, ("file", "sha256", "bytes", "width", "height"))
        integer(image["bytes"], 1, MAX_IMAGE)
        integer(image["width"], 1, 4096); integer(image["height"], 1, 4096)
        _hash(image["sha256"])
        if image["file"] != "images/" + image["sha256"] + ".png":
            raise ValueError("Image path does not match its snapshot identity")
        _, info = _png(safe_path(folder, image["file"]))
        if image != {"file": image["file"], **info}:
            raise ValueError("Reference image changed")
        total += info["bytes"]; pixels += info["width"] * info["height"]
        if total > MAX_TOTAL or pixels > 32 * 1024 * 1024:
            raise ValueError("Board exceeds its total image budget")
        if ref["target"] is not None:
            if value["project"] is None:
                raise ValueError("Asset binding requires a project")
            exact(ref["target"], ("path", "sha256", "bytes"))
            safe_path(Path.cwd(), ref["target"]["path"])
            _hash(ref["target"]["sha256"])
            integer(ref["target"]["bytes"], 0, 512 * 1024 * 1024)
        if ref["recipe"] is not None:
            specification(ref["recipe"])
    return value


def _reference(board, reference_id):
    identifier(reference_id)
    return next((r for r in board["references"] if r["id"] == reference_id), None)


def _edit(folder, revision, action):
    folder = Path(folder)
    integer(revision, 0, 999999)
    if not safe_path(folder, "board.json").is_file():
        raise ValueError("Reference board does not exist")
    with closing(OwnerLock(safe_path(folder, "edit.lock"))):
        board = load(folder)
        if board["revision"] != revision:
            raise ValueError("Board changed; reload before editing")
        action(board)
        board["revision"] += 1
        if len(json.dumps(board, indent=2, allow_nan=False).encode("utf-8")) + 1 > 1024 * 1024:
            raise ValueError("Board metadata exceeds 1 MiB")
        write_json(safe_path(folder, "board.json"), board)
    return board


def add(folder, revision, reference_id, image, title, notes=""):
    identifier(reference_id); text(title, 128, empty=False); text(notes)
    data, info = _png(image)
    def action(board):
        if _reference(board, reference_id) is not None or len(board["references"]) >= 16:
            raise ValueError("Reference already exists or board is full")
        if (sum(r["image"]["bytes"] for r in board["references"]) + len(data) > MAX_TOTAL
                or sum(r["image"]["width"] * r["image"]["height"] for r in board["references"])
                + info["width"] * info["height"] > 32 * 1024 * 1024):
            raise ValueError("Board exceeds its total image budget")
        filename = "images/" + info["sha256"] + ".png"
        path = safe_path(folder, filename)
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError("Existing image snapshot differs")
        else:
            with path.open("xb") as stream:
                stream.write(data)
        board["references"].append({"id": reference_id, "title": title, "notes": notes,
            "image": {"file": filename, **info}, "annotations": [], "target": None, "recipe": None})
    return _edit(folder, revision, action)


def edit(folder, revision, reference_id, *, notes=None, regions=None, recipe=None):
    if notes is not None:
        text(notes)
    if regions is not None:
        regions = annotations(regions)
    if recipe is not None:
        recipe = specification(recipe)
    def action(board):
        ref = _reference(board, reference_id)
        if ref is None:
            raise ValueError("Unknown reference")
        if notes is not None:
            ref["notes"] = notes
        if regions is not None:
            ref["annotations"] = regions
        if recipe is not None:
            if any(s["reference_sha256"] != ref["image"]["sha256"] for s in recipe["sources"].values()):
                raise ValueError("Recipe GLB provenance refers to a different reference")
            ref["recipe"] = recipe
    return _edit(folder, revision, action)


def _game(board):
    from .game_project import GameProject
    if board["project"] is None:
        raise ValueError("Board has no linked game project")
    game = GameProject(board["project"]["root"])
    if game._project_identity() != board["project"]["identity"]:
        raise ValueError("Game project identity changed")
    return game


def _target(game, relative):
    info = game._asset(relative)
    if info["git_lfs_pointer"] or info["bytes"] > 512 * 1024 * 1024:
        raise ValueError("Fetch the real asset and respect the 512 MiB binding limit")
    return {"path": relative, "bytes": info["bytes"], "sha256": digest(safe_path(game.root, relative))}


def link(folder, revision, reference_id, target):
    def action(board):
        ref = _reference(board, reference_id)
        if ref is None:
            raise ValueError("Unknown reference")
        ref["target"] = _target(_game(board), target)
    return _edit(folder, revision, action)


def target_status(board, ref):
    if ref["target"] is None:
        return "not_linked"
    try:
        current = _target(_game(board), ref["target"]["path"])
    except (ValueError, OSError, RuntimeError):
        return "unavailable"
    return "unchanged" if current == ref["target"] else "changed"


def context(folder):
    board = load(folder)
    return {"schema": "cryptonyan.reference-context/1", "board_identity": identity(board),
            "board": board, "targets": {r["id"]: target_status(board, r) for r in board["references"]},
            "image_paths": {r["id"]: str(safe_path(folder, r["image"]["file"])) for r in board["references"]},
            "visual_interpretation_required": True, "generation_submitted": False}


def prepare_reference(folder, revision, reference_id, output, source_root=None):
    folder, output = Path(folder).resolve(), Path(output).absolute()
    _separate(folder, output)
    with closing(OwnerLock(safe_path(folder, "edit.lock"))):
        board = load(folder)
        integer(revision, 0, 1000000)
        if board["revision"] != revision:
            raise ValueError("Board changed; reload before preparing")
        if board["project"]:
            _separate(output, board["project"]["root"])
        ref = _reference(board, reference_id)
        if ref is None or ref["recipe"] is None:
            raise ValueError("Attach an explicit Image Workshop recipe first")
        if target_status(board, ref) not in ("unchanged", "not_linked"):
            raise ValueError("Linked asset changed or is unavailable; review and rebind explicitly")
        plan = prepare(safe_path(folder, ref["image"]["file"]), ref["recipe"], output, source_root)
        trace = {"schema": "cryptonyan.board-handoff/1", "board_identity": identity(board),
                 "board_id": board["id"], "revision": board["revision"], "reference": ref,
                 "project_identity": board["project"]["identity"] if board["project"] else None,
                 "plan_identity": plan["identity"], "generation_submitted": False}
        write_json(output / "reference-context.json", trace)
        return trace


def export_html(folder, output):
    board = load(folder)
    output = Path(output)
    _separate(folder, output)
    if board["project"]:
        _separate(output, board["project"]["root"])
    cards = []
    for ref in board["references"]:
        data, _ = _png(safe_path(folder, ref["image"]["file"]))
        marks = []
        for index, mark in enumerate(ref["annotations"], 1):
            x, y, w, h = [v * 1000 for v in mark["rect"]]
            marks.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>'
                         f'<text x="{x + 4}" y="{y + 22}">{index}</text>')
        notes = "".join("<li>" + html.escape(m["text"]) + "</li>" for m in ref["annotations"])
        target = ref["target"]["path"] if ref["target"] else "Aucun asset lié"
        cards.append('<article><h2>' + html.escape(ref["title"]) + '</h2><div class="picture">'
            '<img alt="Référence" src="data:image/png;base64,' + base64.b64encode(data).decode() + '">'
            '<svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">'
            + ''.join(marks) + '</svg></div><p class="notes">' + html.escape(ref["notes"])
            + '</p><ol>' + notes + '</ol><p>' + html.escape(target) + ' — '
            + target_status(board, ref) + '</p><p>Recette : '
            + (html.escape(ref["recipe"]["id"]) if ref["recipe"] else 'à fournir') + '</p></article>')
    document = ('<!doctype html><html lang="fr"><meta charset="utf-8"><title>' + html.escape(board["title"])
        + '</title><style>body{font:16px system-ui;background:#171a24;color:#eee;margin:2rem}'
        'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem}'
        'article{padding:1rem;background:#252a38;border-radius:12px}.picture{position:relative}'
        'img{width:100%;display:block}svg{position:absolute;inset:0;width:100%;height:100%}'
        'rect{fill:none;stroke:#ffd166;stroke-width:3}text{fill:#ffd166;font:bold 24px sans-serif}'
        '.notes{white-space:pre-wrap}li{margin:.5rem 0}</style><h1>' + html.escape(board["title"])
        + '</h1><p>Révision ' + str(board["revision"]) + ' — annotations, pas de génération automatique.</p><main>'
        + ''.join(cards) + '</main></html>')
    # Explicit output, never replace an existing review or game file.
    with output.open("x", encoding="utf-8") as stream:
        stream.write(document)
    return {"output": str(output.resolve()), "board_identity": identity(board)}


class ReferenceService:
    """Read-only MCP view of an operator-selected library; no arbitrary file reads."""
    def __init__(self, root):
        self.root = Path(root).resolve()

    def boards(self):
        if not self.root.exists():
            return {"boards": []}
        result = []
        for folder in sorted(self.root.iterdir()):
            if folder.is_symlink() or not folder.is_dir() or not (folder / "board.json").is_file():
                continue
            identifier(folder.name)
            if len(result) >= 64:
                raise ValueError("Reference library exceeds 64 boards")
            value = load(folder)
            result.append({"board_id": folder.name, "title": value["title"], "revision": value["revision"],
                           "references": len(value["references"])})
        return {"boards": result}

    def read(self, board_id):
        return context(safe_path(self.root, identifier(board_id)))

    def image(self, board_id, reference_id):
        folder = safe_path(self.root, identifier(board_id))
        board = load(folder)
        ref = _reference(board, reference_id)
        if ref is None:
            raise ValueError("Unknown reference")
        if ref["image"]["bytes"] > 2 * 1024 * 1024:
            raise ValueError("MCP images are limited to 2 MiB; use the local snapshot or add a smaller reference")
        data, info = _png(safe_path(folder, ref["image"]["file"]))
        if info["sha256"] != ref["image"]["sha256"]:
            raise ValueError("Reference changed")
        return {"type": "image", "mimeType": "image/png", "data": base64.b64encode(data).decode("ascii")}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reference boards for existing assets and Image Workshop")
    sub = parser.add_subparsers(dest="action", required=True)
    new = sub.add_parser("create"); new.add_argument("folder", type=Path)
    new.add_argument("--id", required=True); new.add_argument("--title", required=True); new.add_argument("--project", type=Path)
    for action in ("add", "edit", "link", "recipe", "prepare"):
        p = sub.add_parser(action); p.add_argument("folder", type=Path)
        p.add_argument("--revision", type=int, required=True); p.add_argument("--reference", required=True)
        if action == "add":
            p.add_argument("--image", type=Path, required=True); p.add_argument("--title", required=True)
            p.add_argument("--notes", default="")
        elif action == "edit":
            p.add_argument("--notes"); p.add_argument("--annotations", type=Path)
        elif action == "link":
            p.add_argument("--target", required=True)
        elif action == "recipe":
            p.add_argument("--recipe", type=Path, required=True)
        else:
            p.add_argument("--output", type=Path, required=True); p.add_argument("--source-root", type=Path)
    p = sub.add_parser("read"); p.add_argument("folder", type=Path)
    p = sub.add_parser("html"); p.add_argument("folder", type=Path); p.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    from .animation_doctor import read_json
    if args.action == "create":
        result = create(args.folder, args.id, args.title, args.project)
    elif args.action == "add":
        result = add(args.folder, args.revision, args.reference, args.image, args.title, args.notes)
    elif args.action == "edit":
        result = edit(args.folder, args.revision, args.reference, notes=args.notes,
                      regions=read_json(args.annotations) if args.annotations else None)
    elif args.action == "link":
        result = link(args.folder, args.revision, args.reference, args.target)
    elif args.action == "recipe":
        result = edit(args.folder, args.revision, args.reference, recipe=read_json(args.recipe))
    elif args.action == "prepare":
        result = prepare_reference(args.folder, args.revision, args.reference, args.output, args.source_root)
    elif args.action == "html":
        result = export_html(args.folder, args.output)
    else:
        result = context(args.folder)
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, RuntimeError):
        parser_message = "Reference operation failed; check revision, identifiers, source integrity and output paths."
        raise SystemExit(parser_message)
