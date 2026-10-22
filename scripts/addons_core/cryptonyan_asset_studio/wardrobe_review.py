# SPDX-License-Identifier: GPL-3.0-or-later
"""Animated try-on of existing skinned garments; never fit, repaint or replace assets."""
import argparse
import csv
import html
import json
from pathlib import Path
import shutil
import sys
import threading
import time

from .animation_doctor import exact, name, number, parse_capture, read_json
from .creative_director import integer
from .executors import BudgetExpired, ExecutionContext, WorkerFailure, run_process
from .storage import digest, write_json


def specification(value):
    exact(value, ("schema", "armature", "body", "garments", "captures", "tolerance_m", "max_influences"))
    if value["schema"] != "cryptonyan.wardrobe-review/1":
        raise ValueError("Unsupported wardrobe review schema")
    name(value["armature"]); name(value["body"])
    garments = value["garments"]
    if not isinstance(garments, list) or not 1 <= len(garments) <= 8:
        raise ValueError("Select 1 to 8 already skinned garments")
    garments = [name(g) for g in garments]
    if len(set([value["body"], value["armature"], *garments])) != len(garments)+2:
        raise ValueError("Body, rig and garments must be distinct")
    if not isinstance(value["captures"], list) or not 1 <= len(value["captures"]) <= 8:
        raise ValueError("Select 1 to 8 animation windows")
    captures = [parse_capture(c) for c in value["captures"]]
    windows = [(c["action"], c.get("action_slot"), c["start_frame"], c["end_frame"], c["step_frames"]) for c in captures]
    if len(set(windows)) != len(windows) or any(c["armature"] != value["armature"] for c in captures):
        raise ValueError("Use distinct windows on the selected rig")
    if sum((c["end_frame"]-c["start_frame"])//c["step_frames"]+1 for c in captures) > 240:
        raise ValueError("At most 240 total sampled frames")
    number(value["tolerance_m"], .00001, .01)
    integer(value["max_influences"], 1, 8)
    return {**value, "garments": garments, "captures": captures}


def rank(sample):
    """Stable worst-frame order: depth, suspect vertices, crossing edges."""
    return (sample["max_depth_m"], sample["negative_signed_distance_vertices"], sample["surface_crossing_edges"])


def tables(report, output):
    """Offline, escaped review; no external resources and no script execution."""
    output = Path(output)
    rows = []
    with (output / "samples.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("window", "action", "garment", "frame", "time_s", "suspect_vertices", "max_depth_m", "surface_crossing_edges"))
        for clip in report["clips"]:
            for garment in clip["garments"]:
                for sample in garment["samples"]:
                    def cell(value):
                        return "'"+value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
                    writer.writerow([cell(v) for v in (clip["index"], clip["capture"]["action"], garment["name"],
                        sample["frame"], sample["time_s"], sample["negative_signed_distance_vertices"],
                        sample["max_depth_m"], sample["surface_crossing_edges"])])
                worst = garment["worst"]
                values = (clip["index"], clip["capture"]["action"], garment["name"], worst["frame"],
                          garment["flagged_frames"], f'{worst["max_depth_m"]*1000:.3f}', worst["surface_crossing_edges"])
                rows.append("<tr>"+"".join("<td>"+html.escape(str(v))+"</td>" for v in values)+"</tr>")
    links = " ".join('<a href="'+clip["review_file"]+'">Copie '+str(clip["index"])+"</a>" for clip in report["clips"])
    page = ('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Essayage animé</title>'
            '<style>body{font:16px system-ui;max-width:1100px;margin:2em auto;padding:1em}'
            'td,th{padding:.5em;border:1px solid #999}table{border-collapse:collapse}</style>'
            '<h1>Essayage animé — revue requise</h1><p>Signes de distance au triangle le plus proche et '
            'traversées d’arêtes par rayons BVH : diagnostic échantillonné, sans certification de collision ni de tissu.</p>'
            '<p>Les vêtements sont évalués séparément contre le corps ; aucune collision vêtement/vêtement.</p>'
            '<p>'+links+'</p><p><a href="samples.csv">Toutes les frames (CSV)</a> · '
            '<a href="wardrobe.json">Rapport JSON</a></p><table><tr><th>Fenêtre</th><th>Action</th><th>Vêtement</th>'
            '<th>Pire frame</th><th>Frames signalées</th><th>Profondeur estimée mm</th><th>Arêtes traversantes</th></tr>'
            +"".join(rows)+'</table><p>Chaque copie ouvre la pire pose globale de sa fenêtre. '
            'Les marqueurs CN_WR indiquent les frames signalées. NLA désactivé dans les copies.</p></html>')
    (output / "review.html").write_text(page, encoding="utf-8")


def run(source, spec, output, blender, timeout=180):
    spec = specification(spec); number(timeout, 1, 600)
    source, output, binary = Path(source).resolve(), Path(output).resolve(), Path(blender).resolve()
    if source.suffix.lower() != ".blend" or not source.is_file() or not 1 <= source.stat().st_size <= 512*1024*1024:
        raise ValueError("Require a self-contained .blend of at most 512 MiB")
    if not binary.is_file():
        raise ValueError("Blender executable missing")
    before = digest(source)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = {"schema": "cryptonyan.wardrobe-result/1", "status": "running", "source_sha256": before,
               "visual_quality_validated": False, "surface_collision_certified": False, "copies": []}
    try:
        shutil.copyfile(source, output / "source.blend")
        if digest(source) != before or digest(output / "source.blend") != before:
            raise ValueError("Source changed during snapshot")
        write_json(output / "request.json", spec)
        context = ExecutionContext(output, output, ("source.blend",), threading.Event(), time.monotonic()+timeout)
        run_process([str(binary), "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                     "--python-exit-code", "1", "--python", str(Path(__file__).with_name("wardrobe_worker.py")),
                     "--", str(output / "request.json")], context)
        if digest(source) != before or digest(output / "source.blend") != before:
            raise ValueError("Source changed during review")
        report = read_json(output / "wardrobe.json")
        if len(report["clips"]) != len(spec["captures"]):
            raise ValueError("Incomplete review")
        copies = []
        for index, clip in enumerate(report["clips"], 1):
            if clip["review_file"] != f"review-{index:02d}.blend":
                raise ValueError("Unexpected review filename")
            copies.append({"file": clip["review_file"], "sha256": digest(output / clip["review_file"])})
        report["source_sha256"] = before
        write_json(output / "wardrobe.json", report)
        tables(report, output)
        receipt.update(status="review_required", flagged_samples=report["flagged_samples"], copies=copies,
                       weight_findings=len(report["weight_audit"]["findings"]))
        return receipt
    except Exception as error:
        receipt.update(status="failed", error=type(error).__name__)
        raise
    finally:
        write_json(output / "result.json", receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Review existing skinned clothes over multiple actions on isolated copies")
    parser.add_argument("source", type=Path); parser.add_argument("specification", type=Path)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)
    receipt = run(args.source, read_json(args.specification), args.output, args.blender, args.timeout)
    print(json.dumps(receipt))
    return 1 if receipt["flagged_samples"] or receipt["weight_findings"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, WorkerFailure, BudgetExpired) as error:
        print("Wardrobe review failed: "+type(error).__name__, file=sys.stderr)
        raise SystemExit(2)
