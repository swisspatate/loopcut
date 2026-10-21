# SPDX-License-Identifier: GPL-3.0-or-later
"""Internal subprocess entry point; accepts only a service-created request file."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptonyan_asset_studio.asset_doctor import audit_blender, audit_fixture
from cryptonyan_asset_studio.schema import Mission
from cryptonyan_asset_studio.storage import write_json


def main():
    request_path = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    mission = Mission.parse(request["mission"])
    reports = []
    publication = None
    for i, snapshot in enumerate(request["snapshots"]):
        if request["mode"] == "blender":
            import bpy
            bpy.ops.wm.open_mainfile(filepath=snapshot, load_ui=False, use_scripts=False)
            result = audit_blender(mission.target_assets, mission.success_criteria,
                                   repair_copy=mission.constraints.repair_copy)
            if mission.type == "asset_publish" and result["passed"]:
                from cryptonyan_asset_studio.asset_publisher import export_static_mesh
                publication = export_static_mesh(mission, snapshot, request_path.parent, result)
            if result["repairs"]:
                bpy.ops.wm.save_as_mainfile(filepath=str(request_path.parent / f"repaired-{i}.blend"),
                                          copy=True, check_existing=False)
        else:
            result = audit_fixture(snapshot, mission.target_assets, mission.success_criteria)
        result["input_index"] = i
        reports.append(result)
    write_json(request_path.parent / "quality.json", {
        "schema": "cryptonyan.quality-batch/1", "reports": reports,
        "passed": bool(reports) and all(report["passed"] for report in reports)})
    if publication is not None:
        from cryptonyan_asset_studio.publication import seal_manifest
        seal_manifest(publication, request_path.parent)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never persist Blender tracebacks, input contents or arbitrary exception messages.
        code = "blender_error"
        from cryptonyan_asset_studio.executors import WorkerFailure
        if isinstance(error, WorkerFailure):
            code = error.code
        elif isinstance(error, ValueError):
            code = "target_not_found" if str(error) == "Target asset not found" else "invalid_asset"
            if str(error) in ("Mesh exceeds MVP complexity budget", "Scene object budget exceeded",
                              "Mesh exceeds MVP complexity budget or has invalid arrays",
                              "Mesh corner budget exceeded or invalid faces"):
                code = "complexity_budget"
        elif isinstance(error, ImportError):
            code = "runtime_missing"
        elif isinstance(error, FileNotFoundError):
            code = "missing_dependency"
        request_path = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
        write_json(request_path.parent / "worker_error.json", {"code": code})
        raise SystemExit(1)
