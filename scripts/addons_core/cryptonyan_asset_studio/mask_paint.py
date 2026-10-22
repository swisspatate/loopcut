# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline image-space mask painting; replayable strokes, fixed reference and PBR PNG."""
import argparse
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil

from .animation_doctor import exact, number, read_json
from .creative_director import integer
from .image_workshop import identity
from .materials import read_png
from .png_pixels import encode, MAX_PIXELS
from .publication import _hash
from .reference_board import text, identifier
from .storage import safe_path, write_json

SCHEMA = "cryptonyan.mask-paint/1"
MAX_WORK = 32 * 1024 * 1024


def _reference(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Use a regular PNG of at most 8 MiB")
    payload, size = read_png(path)
    if size["width"] * size["height"] > MAX_PIXELS:
        raise ValueError("Mask editor supports at most one megapixel")
    return payload, {"sha256": hashlib.sha256(payload).hexdigest(), **size}


def specification(value):
    value = copy.deepcopy(value)
    exact(value, ("schema", "reference", "intent", "strokes"))
    if value["schema"] != SCHEMA:
        raise ValueError("Unsupported mask painting schema")
    ref = value["reference"]
    exact(ref, ("sha256", "width", "height")); _hash(ref["sha256"])
    integer(ref["width"], 1, 4096); integer(ref["height"], 1, 4096)
    if ref["width"] * ref["height"] > MAX_PIXELS:
        raise ValueError("Mask exceeds one megapixel")
    text(value["intent"], 512)
    if not isinstance(value["strokes"], list) or len(value["strokes"]) > 128:
        raise ValueError("Use at most 128 strokes")
    total = 0
    for stroke in value["strokes"]:
        exact(stroke, ("mode", "radius_px", "value", "points"))
        if stroke["mode"] not in ("paint", "erase"):
            raise ValueError("Unsupported brush mode")
        integer(stroke["radius_px"], 1, 128); integer(stroke["value"], 0, 255)
        points = stroke["points"]
        if not isinstance(points, list) or not 1 <= len(points) <= 512:
            raise ValueError("Use one to 512 points per stroke")
        total += len(points)
        if total > 4096:
            raise ValueError("Mask exceeds 4096 brush points")
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("Expected normalized x/y brush position")
            for coordinate in point: number(coordinate, 0, 1)
    return value


def rasterize(value):
    value = specification(value)
    width, height = value["reference"]["width"], value["reference"]["height"]
    mask = bytearray(width * height)
    work = 0
    for stroke in value["strokes"]:
        radius = stroke["radius_px"]
        points = [(p[0]*width, p[1]*height) for p in stroke["points"]]
        segments = list(zip(points, points[1:])) if len(points) > 1 else [(points[0], points[0])]
        for (ax, ay), (bx, by) in segments:
            x0, x1 = max(0, math.floor(min(ax,bx)-radius)), min(width-1, math.floor(max(ax,bx)+radius))
            y0, y1 = max(0, math.floor(min(ay,by)-radius)), min(height-1, math.floor(max(ay,by)+radius))
            work += (x1-x0+1)*(y1-y0+1)
            if work > MAX_WORK:
                raise ValueError("Brush work exceeds 32 M pixel checks; simplify strokes")
            dx, dy = bx-ax, by-ay
            length2 = dx*dx + dy*dy
            for y in range(y0, y1+1):
                for x in range(x0, x1+1):
                    t = max(0, min(1, ((x+.5-ax)*dx+(y+.5-ay)*dy)/length2)) if length2 else 0
                    if (x+.5-ax-t*dx)**2+(y+.5-ay-t*dy)**2 <= radius*radius:
                        mask[y*width+x] = 0 if stroke["mode"] == "erase" else stroke["value"]
    return mask


def editor(reference, output):
    payload, info = _reference(reference)
    project = {"schema": SCHEMA, "reference": info, "intent": "", "strokes": []}
    data = json.dumps({"project": project, "image": base64.b64encode(payload).decode("ascii")}).replace("<", "\\u003c")
    script = Path(__file__).with_name("mask_editor.js").read_text(encoding="utf-8")
    page = '''<!doctype html><html lang="fr"><meta charset="utf-8"><title>CryptoNyan — Masque</title>
<style>body{font:16px system-ui;background:#202329;color:#eee;margin:1rem}button,input,select{font:inherit;margin:.3rem}#surface{position:relative;display:inline-block;max-width:100%;line-height:0}canvas{max-width:100%;height:auto;touch-action:none}#paint{position:absolute;inset:0;width:100%;height:100%;cursor:crosshair}#status{white-space:pre-wrap}label{display:inline-block}</style>
<h1>Peindre un masque</h1><p>Image uniquement. Noir : conserver ; blanc : appliquer ; gris : mélange. Aucun envoi réseau.</p>
<label>Intention <input id="intent" maxlength="512" placeholder="Neige sur le toit"></label><br>
<label>Outil <select id="mode"><option value="paint">Pinceau</option><option value="erase">Gomme</option></select></label>
<label>Rayon (pixels image) <input id="radius" type="number" min="1" max="128" value="12"></label>
<label>Valeur du masque <input id="value" type="number" min="0" max="255" value="255"></label>
<button id="undo">Annuler le trait</button><button id="redo">Rétablir</button>
<button id="save">Enregistrer le tracé JSON</button><label>Reprendre un tracé <input id="load" type="file" accept=".json,application/json"></label>
<p id="status">Chargement de l'image…</p><div id="surface"><canvas id="reference"></canvas><canvas id="paint"></canvas></div>
<p>Réimporter le JSON dans Blender pour produire le PNG vérifié. Le masque est dessiné dans l'image ; il n'est pas projeté automatiquement sur un modèle 3D.</p>
<script>const CRYPTONYAN_DATA=__DATA__;</script><script>__SCRIPT__</script></html>'''
    page = page.replace("__DATA__", data).replace("__SCRIPT__", script)
    output = Path(output)
    with output.open("x", encoding="utf-8") as stream: stream.write(page)
    return {"reference": info, "editor": str(output.resolve()), "network_used": False}


def render(project, reference, output):
    project = specification(project)
    payload, ref = _reference(reference)
    if project["reference"] != ref:
        raise ValueError("Painting belongs to a different reference image")
    mask = rasterize(project)
    rgb = bytearray(len(mask)*3)
    for channel in range(3): rgb[channel::3] = mask
    png = encode(ref["width"], ref["height"], rgb)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        (output / "reference.png").write_bytes(payload)
        (output / "mask.png").write_bytes(png)
        write_json(output / "strokes.json", project)
        value = {"schema": "cryptonyan.mask-bundle/1", "project_identity": identity(project), "reference": ref,
                 "mask": {"file": "mask.png", "sha256": hashlib.sha256(png).hexdigest(), "bytes": len(png),
                          "width": ref["width"], "height": ref["height"], "color_space": "Non-Color"},
                 "mapping": "image_coordinates_top_left_not_automatic_UV_projection"}
        value["identity"] = identity(value)
        write_json(output / "mask.json", value)
        return load_bundle(output)
    except BaseException:
        shutil.rmtree(output)
        raise


def load_bundle(folder):
    folder = Path(folder)
    for name in ("strokes.json", "mask.json"):
        if safe_path(folder, name).stat().st_size > 1024*1024:
            raise ValueError("Mask metadata exceeds one MiB")
    project = specification(read_json(safe_path(folder, "strokes.json")))
    payload, ref = _reference(safe_path(folder, "reference.png"))
    if project["reference"] != ref:
        raise ValueError("Mask reference changed")
    mask = rasterize(project)
    rgb = bytearray(len(mask)*3)
    for channel in range(3): rgb[channel::3] = mask
    expected_png = encode(ref["width"], ref["height"], rgb)
    value = read_json(safe_path(folder, "mask.json"))
    expected = {"schema": "cryptonyan.mask-bundle/1", "project_identity": identity(project), "reference": ref,
                "mask": {"file": "mask.png", "sha256": hashlib.sha256(expected_png).hexdigest(), "bytes": len(expected_png),
                         "width": ref["width"], "height": ref["height"], "color_space": "Non-Color"},
                "mapping": "image_coordinates_top_left_not_automatic_UV_projection"}
    expected["identity"] = identity(expected)
    path = safe_path(folder, "mask.png")
    if path.stat().st_size != len(expected_png) or path.read_bytes() != expected_png or value != expected:
        raise ValueError("Mask bundle or replayed strokes changed")
    return value


class MaskService:
    """Read-only view of masks deliberately published in the approved library."""
    def __init__(self, library):
        self.root = safe_path(library, "masks")
        if (self.root / "board.json").exists():
            raise ValueError("masks namespace is occupied by a reference board")

    def _folder(self, mask_id):
        return safe_path(self.root, identifier(mask_id))

    def list(self):
        if not self.root.exists():
            return {"masks": []}
        result = []
        for folder in sorted(self.root.iterdir()):
            if folder.is_symlink() or not folder.is_dir() or not (folder / "mask.json").is_file():
                continue
            if len(result) >= 64:
                raise ValueError("Library exceeds 64 masks")
            value = self.read(folder.name)
            result.append({"mask_id": folder.name, "identity": value["bundle"]["identity"],
                           "intent": value["painting"]["intent"], "reference": value["bundle"]["reference"]})
        return {"masks": result}

    def read(self, mask_id):
        folder = self._folder(mask_id)
        bundle = load_bundle(folder)
        return {"bundle": bundle, "painting": read_json(safe_path(folder, "strokes.json"))}

    def image(self, mask_id, kind):
        if kind not in ("mask", "reference"):
            raise ValueError("Choose mask or reference image")
        value = self.read(mask_id)
        path = safe_path(self._folder(mask_id), kind + ".png")
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("MCP images are limited to two MiB")
        payload, _ = read_png(path)
        expected = value["bundle"][kind]["sha256"]
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("Mask image changed")
        return {"type": "image", "mimeType": "image/png", "data": base64.b64encode(payload).decode("ascii")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    edit = sub.add_parser("editor"); edit.add_argument("reference", type=Path); edit.add_argument("--output", required=True, type=Path)
    paint = sub.add_parser("render"); paint.add_argument("project", type=Path); paint.add_argument("--reference", required=True, type=Path); paint.add_argument("--output", required=True, type=Path)
    check = sub.add_parser("check"); check.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    result = editor(args.reference, args.output) if args.command == "editor" else render(read_json(args.project), args.reference, args.output) if args.command == "render" else load_bundle(args.folder)
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
