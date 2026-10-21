# SPDX-License-Identifier: GPL-3.0-or-later
"""One material variant in an isolated Blender process; never saves source scenes."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptonyan_asset_studio.storage import digest, safe_path, write_json


def build(request):
    from cryptonyan_asset_studio.asset_doctor import audit_blender
    from cryptonyan_asset_studio.asset_publisher import export_static_mesh
    from cryptonyan_asset_studio.blender_materials import apply_material_copy
    from cryptonyan_asset_studio.publication import seal_manifest
    from cryptonyan_asset_studio.schema import Mission
    job = request["job"]
    source = safe_path(request["snapshots"], job["source"])
    material = safe_path(request["snapshots"], job["material"])
    if digest(source) != request["source_sha256"] or digest(material) != request["material_sha256"]:
        raise ValueError("Theme inputs changed before worker startup")
    output = Path(request["output"]).resolve(strict=True)
    prepared = safe_path(output, "asset.blend")
    apply_material_copy(source, material, job["object"], prepared)
    mission = Mission.parse({"type": "asset_publish", "inputs": ["asset.blend"], "target_assets": [job["object"]]})
    audit = audit_blender(mission.target_assets, mission.success_criteria)
    if not audit["passed"]:
        raise ValueError("Prepared variant failed Asset Doctor")
    manifest = export_static_mesh(mission, prepared, output, audit)
    write_json(output / "quality.json", {"schema": "cryptonyan.quality-batch/1", "passed": True, "reports": [audit]})
    seal_manifest(manifest, output)
    if digest(source) != request["source_sha256"]:
        raise ValueError("Theme source changed during build")


if __name__ == "__main__":
    from cryptonyan_asset_studio.runner_kit import read_json
    from cryptonyan_asset_studio.executors import WorkerFailure
    request = Path(sys.argv[sys.argv.index("--") + 1]).resolve(strict=True)
    try:
        build(read_json(request))
    except Exception as error:
        code = error.code if isinstance(error, WorkerFailure) else "invalid_asset" if isinstance(error, ValueError) else "blender_error"
        write_json(request.parent / "worker_error.json", {"code": code})
        raise SystemExit(1)
