# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only, bounded comparison of a texture profile with ComfyUI /object_info.

This is a static diagnostic, not ComfyUI's execution/VALIDATE_INPUTS machinery.
No inference, downloads, queue changes or proof of model provenance occurs here.
"""
import copy
import json
import math

from .comfyui_adapter import ComfyError, LocalHTTP, workflow_digest

MAX_INFO_BYTES = 8 * 1024 * 1024
MAX_NODES = 256
MAX_ISSUES = 100
PRIMITIVES = {"INT", "FLOAT", "STRING", "BOOLEAN"}


def _reject_constant(_value):
    raise ValueError("Nonfinite metadata number")


def validate_parameters(prompt, seed):
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4096 or "\x00" in prompt:
        raise ComfyError("Prompt must contain 1-4096 characters without NUL")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ComfyError("Seed must be an unsigned 64-bit integer")


def inspect_profile(profile, object_info, prompt, seed):
    """Compare the effective prompt/seed graph without changing the approved template."""
    validate_parameters(prompt, seed)
    workflow = copy.deepcopy(profile["template"])
    for bindings, value in ((profile["prompt_inputs"], prompt), (profile["seed_inputs"], seed)):
        for node, name in bindings:
            workflow[node]["inputs"][name] = value
    report = {"schema": "cryptonyan.comfy-preflight/1", "profile": profile["id"],
              "template_sha256": profile["workflow_sha256"], "effective_workflow_sha256": workflow_digest(workflow),
              "status": "compatible", "issues": [], "error_count": 0, "review_count": 0,
              "omitted_issues": 0, "node_count": len(workflow), "checked_choices": 0,
              "submission_performed": False, "gpu_execution_validated": False,
              "model_provenance_verified": False, "distribution_approved": False,
              "unchecked": ["custom_node_validation", "model_bytes_and_licenses", "gpu_memory",
                            "saved_png_count_and_format", "visual_quality"]}

    def issue(severity, code, node=None, name=None):
        report["error_count" if severity == "error" else "review_count"] += 1
        item = {"severity": severity, "code": code}
        if node is not None:
            item["node"] = node[:256]
        if name is not None:
            item["input"] = name[:256]
        if len(report["issues"]) < MAX_ISSUES:
            report["issues"].append(item)
        else:
            report["omitted_issues"] += 1

    def finish():
        report["status"] = "blocked" if report["error_count"] else "needs_review" if report["review_count"] else "compatible"
        return report

    if not isinstance(object_info, dict) or not object_info:
        issue("review", "invalid_object_info")
        return finish()
    if len(workflow) > MAX_NODES:
        issue("error", "workflow_node_budget")
        return finish()
    metadata = {}
    for node, definition in workflow.items():
        info = object_info.get(definition["class_type"])
        if info is None:
            issue("error", "node_unavailable", node)
        elif not isinstance(info, dict) or not isinstance(info.get("input"), dict):
            issue("review", "unsupported_node_metadata", node)
        else:
            metadata[node] = info
            if info.get("api_node"):
                issue("review", "remote_api_node", node)

    dependencies = {node: set() for node in workflow}
    for node, definition in workflow.items():
        inputs = definition["inputs"]
        if len(inputs) > 128:
            issue("error", "node_input_budget", node)
            continue
        info = metadata.get(node, {})
        schema = info.get("input", {})
        required, optional = schema.get("required", {}), schema.get("optional", {})
        if not isinstance(required, dict) or not isinstance(optional, dict):
            issue("review", "unsupported_input_schema", node)
            required, optional = {}, {}
        known = {**required, **optional}
        if len(known) > 128:
            issue("review", "input_schema_budget", node)
            continue
        for name in required.keys() - inputs.keys():
            issue("error", "required_input_missing", node, name)
        for name, value in inputs.items():
            spec = known.get(name)
            if spec is None:
                if node in metadata:
                    issue("review", "undeclared_input", node, name)
                kind, options = None, {}
            elif (not isinstance(spec, list) or not 1 <= len(spec) <= 2
                  or (len(spec) == 2 and not isinstance(spec[1], dict))):
                issue("review", "unsupported_input_schema", node, name)
                kind, options = None, {}
            else:
                kind, options = spec[0], spec[1] if len(spec) == 2 else {}
                if not isinstance(kind, (str, list)) or kind == "":
                    issue("review", "unsupported_input_schema", node, name)
            if options.get("remote") or options.get("dynamic"):
                issue("review", "dynamic_input_unchecked", node, name)
            # API-format lists represent graph links, not UI widget values.
            if isinstance(value, list):
                if len(value) != 2 or not isinstance(value[0], str) or type(value[1]) is not int or value[1] < 0:
                    issue("error", "invalid_link", node, name)
                    continue
                source, index = value
                if source not in workflow:
                    issue("error", "link_node_missing", node, name)
                    continue
                dependencies[node].add(source)
                outputs = metadata.get(source, {}).get("output")
                if not isinstance(outputs, list):
                    issue("review", "unknown_link_output", node, name)
                elif index >= len(outputs):
                    issue("error", "link_output_missing", node, name)
                elif isinstance(kind, str) and isinstance(outputs[index], str):
                    actual = outputs[index]
                    if kind == "*" or actual == "*" or "," in kind or "," in actual or kind == "COMBO":
                        issue("review", "dynamic_link_type", node, name)
                    elif kind != actual:
                        issue("error", "link_type_mismatch", node, name)
                else:
                    issue("review", "dynamic_link_type", node, name)
                continue
            if options.get("forceInput"):
                issue("review", "forced_input_literal", node, name)
            choices = kind if isinstance(kind, list) else options.get("options") if kind == "COMBO" else None
            if choices is not None:
                if not isinstance(choices, list) or any(type(v) not in (str, int, float, bool) for v in choices):
                    issue("review", "unsupported_choices", node, name)
                elif not any(type(value) is type(choice) and value == choice for choice in choices):
                    issue("error", "choice_unavailable", node, name)
                else:
                    report["checked_choices"] += 1
                continue
            if not isinstance(kind, str) or kind not in PRIMITIVES:
                if kind is not None:
                    issue("review", "custom_literal_unchecked", node, name)
                continue
            valid = {"INT": type(value) is int, "FLOAT": type(value) in (int, float),
                     "STRING": type(value) is str, "BOOLEAN": type(value) is bool}[kind]
            if not valid or (type(value) is float and not math.isfinite(value)):
                issue("error", "literal_type_mismatch", node, name)
                continue
            if kind in ("INT", "FLOAT"):
                for bound, compare in (("min", lambda a, b: a < b), ("max", lambda a, b: a > b)):
                    if bound in options:
                        limit = options[bound]
                        if type(limit) not in (int, float) or (type(limit) is float and not math.isfinite(limit)):
                            issue("review", "unsupported_numeric_bound", node, name)
                        elif compare(value, limit):
                            issue("error", "literal_out_of_range", node, name)

    # Bounded topological traversal; include even disconnected nodes conservatively.
    remaining = {node: set(links) for node, links in dependencies.items()}
    while remaining:
        ready = {node for node, links in remaining.items() if not links}
        if not ready:
            issue("error", "workflow_cycle")
            break
        remaining = {node: links - ready for node, links in remaining.items() if node not in ready}
    for node, _image_index in profile["outputs"].values():
        info = metadata.get(node, {})
        if info.get("output_node") is not True:
            issue("error", "channel_not_output_node", node)
        elif workflow[node]["class_type"] != "SaveImage":
            issue("review", "custom_saved_png_output_unchecked", node)
    return finish()


def preflight(profile, endpoint, prompt, seed, *, transport=None):
    """One bounded GET; server failure produces a diagnostic, never a POST retry."""
    validate_parameters(prompt, seed)
    http = LocalHTTP(endpoint)
    try:
        raw = (transport or http)("GET", "/object_info", limit=MAX_INFO_BYTES, timeout=10)
        if not isinstance(raw, bytes) or len(raw) > MAX_INFO_BYTES:
            raise ComfyError("Invalid or oversized metadata")
        info = json.loads(raw, parse_constant=_reject_constant)
        if not isinstance(info, dict) or not info:
            raise ComfyError("Invalid metadata")
        metadata_hash = workflow_digest(info)
    except (ComfyError, OSError, ValueError, TypeError, RecursionError):
        return {"schema": "cryptonyan.comfy-preflight/1", "profile": profile["id"],
                "template_sha256": profile["workflow_sha256"], "status": "unavailable",
                "issues": [{"severity": "error", "code": "object_info_unavailable_or_invalid"}],
                "submission_performed": False, "gpu_execution_validated": False,
                "model_provenance_verified": False, "distribution_approved": False}
    result = inspect_profile(profile, info, prompt, seed)
    result["object_info_sha256"] = metadata_hash
    return result


def main(argv=None):
    import argparse
    from .comfy_profiles import load_catalog, _identifier
    parser = argparse.ArgumentParser(description="Read-only ComfyUI profile preflight; never submits a GPU job")
    parser.add_argument("catalog")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args(argv)
    endpoint, profiles = load_catalog(args.catalog)
    profile = profiles.get(_identifier(args.profile))
    if profile is None:
        raise ComfyError("Unknown texture profile; list configured profiles first")
    result = preflight(profile, endpoint, args.prompt, args.seed)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "compatible" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError):
        import sys
        print("Invalid local profile configuration or parameters.", file=sys.stderr)
        raise SystemExit(2)
