# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic skin-weight plans and isolated, verified Blender candidates."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import time

from .animation_doctor import MAX_JSON, exact, number, read_json
from .executors import BudgetExpired, ExecutionContext, WorkerFailure, WORKER_MESSAGES, run_process
from .rig_doctor import audit_weights, specification
from .storage import digest, safe_path, write_json


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def policy(value):
    exact(value, ("max_influences", "max_removed_fraction"))
    count = value["max_influences"]
    if type(count) is not int or not 1 <= count <= 32:
        raise ValueError("Use 1 to 32 influences")
    return {"max_influences": count, "max_removed_fraction": number(value["max_removed_fraction"], 0, .5)}


def ordered(entries):
    return sorted(entries, key=lambda e: e["group"])


def propose(snapshot, settings, options):
    """Predict exact assignments. Preserve auxiliary groups and skip ambiguous vertices."""
    settings, options = specification(settings), policy(options)
    before = audit_weights(snapshot, settings)
    deform = {b["name"] for b in snapshot["bones"] if b["deform"]}
    operations, manual, predicted = [], [], copy.deepcopy(snapshot)
    for mesh, future in zip(snapshot["meshes"], predicted["meshes"]):
        capture = mesh.get("capture", {})
        if (not isinstance(capture.get("locked_groups"), list) or capture.get("mesh_users") != 1
                or capture.get("library_override") is not False or capture.get("object_mode") != "OBJECT"):
            raise ValueError("Recapture a local single-user mesh in Object Mode with Rig Doctor v0.19")
        groups = mesh["groups"]
        if any(g not in groups for g in capture["locked_groups"]):
            raise ValueError("Unknown locked group")
        locked = set(capture["locked_groups"]) & deform
        issues = {}
        for index, entries in enumerate(mesh["weights"]):
            bone_entries = [e for e in entries if groups[e["group"]] in deform]
            active = [e for e in bone_entries if e["weight"] > settings["weight_epsilon"]]
            reason = None
            if any(not 0 <= e["weight"] <= 1 for e in entries):
                reason = "invalid_weights"
            elif not active:
                reason = "unweighted_vertices"
            elif any(groups[e["group"]] in locked for e in bone_entries):
                reason = "locked_deform_weights"
            if reason is None:
                keep = sorted(active, key=lambda e: (-e["weight"], groups[e["group"]]))[:options["max_influences"]]
                total, retained = sum(e["weight"] for e in bone_entries), sum(e["weight"] for e in keep)
                removed = max(0.0, (total-retained)/total)
                if removed > options["max_removed_fraction"] + 1e-12:
                    reason = "removed_fraction_exceeds_budget"
            if reason:
                evidence = issues.setdefault(reason, {"count": 0, "vertices": []})
                evidence["count"] += 1
                if len(evidence["vertices"]) < 100:
                    evidence["vertices"].append(index)
                continue
            after = ordered([dict(e) for e in entries if groups[e["group"]] not in deform] +
                            [{"group": e["group"], "weight": e["weight"]/retained} for e in keep])
            original = ordered(entries)
            if len(original) == len(after) and all(a["group"] == b["group"] and abs(a["weight"]-b["weight"]) <= 1e-7
                                                   for a, b in zip(original, after)):
                continue
            operations.append({"mesh": mesh["name"], "vertex": index, "before": original, "after": after,
                               "removed_fraction": removed})
            future["weights"][index] = after
        manual.extend({"mesh": mesh["name"], "reason": reason, **evidence,
                       "indices_truncated": evidence["count"] > 100} for reason, evidence in sorted(issues.items()))
    after_settings = {**settings, "max_influences": options["max_influences"]}
    return {"operations": operations, "manual_review": manual, "before_audit": before["identity"],
            "predicted_findings": audit_weights(predicted, after_settings)["findings"],
            "audit_settings": after_settings}


def make_plan(bundle, options):
    bundle = Path(bundle).resolve(strict=True)
    source, weights, audit = (safe_path(bundle, p) for p in ("source.blend", "weights.json", "audit.json"))
    if not 1 <= source.stat().st_size <= 512*1024*1024:
        raise ValueError("Source exceeds snapshot budget")
    snapshot, previous = read_json(weights), read_json(audit)
    provenance = snapshot.get("provenance", {})
    source_hash = digest(source)
    if provenance.get("sampler") != "blender_base_vertex_groups" or provenance.get("source_sha256") != source_hash:
        raise ValueError("Require an unchanged Blender Rig Doctor bundle")
    settings = specification(provenance.get("capture"))
    if previous != audit_weights(snapshot, settings):
        raise ValueError("Audit does not match the captured weights")
    proposal = propose(snapshot, settings, options)
    plan = {"schema": "cryptonyan.rig-repair-plan/1", "bundle": str(bundle), "source_sha256": source_hash,
            "weights_sha256": digest(weights), "audit_sha256": digest(audit), "policy": policy(options),
            "settings": settings, **proposal, "changes_source": False, "visual_quality_validated": False}
    result = {**plan, "identity": identity(plan)}
    if len(json.dumps(result, indent=2, allow_nan=False).encode()) + 1 > MAX_JSON:
        raise ValueError("Repair plan exceeds 32 MiB; reduce the selected meshes")
    return result


def load_plan(path):
    plan = read_json(path)
    if (not isinstance(plan, dict) or plan.get("schema") != "cryptonyan.rig-repair-plan/1"
            or not isinstance(plan.get("bundle"), str) or not isinstance(plan.get("policy"), dict)):
        raise ValueError("Unsupported rig repair plan")
    if plan != make_plan(plan["bundle"], plan["policy"]):
        raise ValueError("Plan or source bundle changed; regenerate and review the plan")
    return plan


def expected_snapshot(snapshot, plan):
    result = copy.deepcopy(snapshot)
    meshes = {m["name"]: m for m in result["meshes"]}
    for op in plan["operations"]:
        meshes[op["mesh"]]["weights"][op["vertex"]] = copy.deepcopy(op["after"])
    return result


def weights_match(actual, expected):
    """Compare all selected assignments, allowing only Blender float32 storage error."""
    if actual["armature"] != expected["armature"] or actual["bones"] != expected["bones"] or len(actual["meshes"]) != len(expected["meshes"]):
        return False
    for a, b in zip(actual["meshes"], expected["meshes"]):
        if any(a[k] != b[k] for k in ("name", "groups", "capture")) or len(a["weights"]) != len(b["weights"]):
            return False
        for row_a, row_b in zip(a["weights"], b["weights"]):
            row_a, row_b = ordered(row_a), ordered(row_b)
            if len(row_a) != len(row_b) or any(x["group"] != y["group"] or abs(x["weight"]-y["weight"]) > 1e-6
                                               for x, y in zip(row_a, row_b)):
                return False
    return True


def execute(plan_path, output, blender=None, *, apply=False, timeout=120):
    if type(apply) is not bool:
        raise ValueError("apply must be boolean")
    number(timeout, 1, 600)
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = load_plan(plan_path)
    bundle = Path(plan["bundle"])
    if output.is_relative_to(bundle):
        raise ValueError("Output must be outside the immutable audit bundle")
    if apply and (blender is None or not Path(blender).is_file()):
        raise ValueError("Blender executable missing")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = {"schema": "cryptonyan.rig-repair-result/1", "plan_identity": plan["identity"],
               "status": "planned", "planned_vertices": len(plan["operations"]), "changed_vertices": None,
               "manual_review": plan["manual_review"], "source_unchanged": None,
               "candidate": None, "visual_quality_validated": False}
    try:
        if not apply:
            return receipt
        if not plan["operations"]:
            receipt.update(status="no_automatic_changes", source_unchanged=True, changed_vertices=0,
                           remaining_findings=plan["predicted_findings"])
            return receipt
        receipt["status"] = "applying"
        shutil.copyfile(bundle / "source.blend", output / "source.blend")
        if digest(output / "source.blend") != plan["source_sha256"]:
            raise ValueError("Snapshot changed during copying")
        write_json(output / "plan.json", plan)
        # Each subprocess gets its own scratch folder; the shared supervisor owns tmp/.
        deadline = time.monotonic() + timeout
        for stage in ("apply", "verify"):
            receipt["status"] = stage
            stage_dir = output / stage
            stage_dir.mkdir()
            write_json(stage_dir / "request.json", {"stage": stage, "output": str(output)})
            context = ExecutionContext(output, stage_dir, ("source.blend",), threading.Event(), deadline)
            run_process([str(Path(blender).resolve()), "--background", "--factory-startup", "--disable-autoexec",
                         "--threads", "1", "--python-exit-code", "1", "--python",
                         str(Path(__file__).with_name("rig_repair_worker.py")), "--", str(stage_dir / "request.json")], context)
            if stage == "apply":
                candidate_hash = digest(output / "candidate.blend")
        if load_plan(plan_path) != plan or digest(output / "source.blend") != plan["source_sha256"]:
            raise ValueError("Source or plan changed during repair")
        if digest(output / "candidate.blend") != candidate_hash:
            raise ValueError("Candidate changed during verification")
        actual = read_json(output / "verified-weights.json")
        expected = expected_snapshot(read_json(bundle / "weights.json"), plan)
        if not weights_match(actual, expected):
            raise WorkerFailure(code="rig_repair_verify")
        audit = audit_weights(actual, plan["audit_settings"])
        write_json(output / "audit.json", audit)
        receipt.update(status="candidate_created_review_required", source_unchanged=True,
                       changed_vertices=len(plan["operations"]),
                       candidate={"file": "candidate.blend", "sha256": candidate_hash},
                       remaining_findings=audit["findings"], verified_after_reopen=True)
        return receipt
    except Exception as error:
        receipt.update(status="failed", error=error.code if isinstance(error, WorkerFailure) else type(error).__name__)
        raise
    finally:
        write_json(output / "result.json", receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan and verify weight repairs on an isolated Blender copy")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("plan")
    prepare.add_argument("bundle", type=Path)
    prepare.add_argument("--policy", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True, help="New JSON plan outside the audit bundle")
    run = sub.add_parser("execute")
    run.add_argument("plan", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--apply", action="store_true")
    run.add_argument("--blender", type=Path)
    run.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)
    if args.command == "plan":
        plan = make_plan(args.bundle, read_json(args.policy))
        if args.output.resolve().is_relative_to(Path(plan["bundle"])):
            raise ValueError("Plan must be outside audit bundle")
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, indent=2, allow_nan=False)
        print(json.dumps({"identity": plan["identity"], "changed_vertices": len(plan["operations"]), "manual_review": plan["manual_review"]}))
        return 0
    receipt = execute(args.plan, args.output, args.blender, apply=args.apply, timeout=args.timeout)
    print(json.dumps(receipt, allow_nan=False))
    return 1 if receipt["manual_review"] or receipt.get("remaining_findings") else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, WorkerFailure, BudgetExpired) as error:
        message = WORKER_MESSAGES[error.code] if isinstance(error, WorkerFailure) else type(error).__name__
        print("Rig repair failed: " + message, file=sys.stderr)
        raise SystemExit(2)
