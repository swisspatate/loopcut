# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage explicit reference PNGs in local ComfyUI input and derive a pinned profile."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

from .comfyui_adapter import ComfyError, workflow_digest
from .materials import read_png
from .storage import safe_path, write_json


def validate_references(profile):
    entries = profile.get("reference_inputs", [])
    if not isinstance(entries, list) or len(entries) > 3:
        raise ComfyError("Use at most three reference images")
    if not entries:
        return
    root = Path(profile.get("input_root", ""))
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise ComfyError("Configure an absolute local ComfyUI input directory")
    seen, total = set(), 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"role", "file", "sha256", "binding"} or entry["role"] not in ("reference", "uv", "mask"):
            raise ComfyError("Invalid reference declaration")
        pair = entry["binding"]
        if (not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(x, str) for x in pair)
                or entry["role"] in seen or tuple(pair) in seen):
            raise ComfyError("Duplicate or invalid reference binding")
        seen.update((entry["role"], tuple(pair)))
        node = profile["template"].get(pair[0], {})
        if node.get("class_type") != "LoadImage" or pair[1] != "image" or node.get("inputs", {}).get("image") != entry["file"]:
            raise ComfyError("Reference must bind an explicit LoadImage.image literal")
        if pair in profile["prompt_inputs"] or pair in profile["seed_inputs"]:
            raise ComfyError("Reference binding overlaps agent parameters")
        if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) or entry["file"] != "cn_"+entry["sha256"]+".png":
            raise ComfyError("Reference filename must match its content hash")
        data, _ = read_png(safe_path(root, entry["file"]))
        total += len(data)
        if total > 64*1024*1024 or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ComfyError("Reference image changed or budget exceeded")


def prepare(catalog, profile_id, references, input_root, output):
    from .comfy_profiles import load_catalog
    endpoint, profiles = load_catalog(catalog)
    if profile_id not in profiles:
        raise ComfyError("Unknown source profile")
    if not isinstance(references, list) or not 1 <= len(references) <= 3:
        raise ComfyError("Declare 1-3 reference/uv/mask files and LoadImage bindings")
    root, output = Path(input_root), Path(output)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ComfyError("ComfyUI input directory must already exist locally")
    selected = copy.deepcopy(profiles[profile_id])
    if selected.get("reference_inputs"):
        raise ComfyError("Derive references from the original approved profile")
    workflow = selected.pop("template")
    selected.pop("input_root", None)
    entries, staged, total, seen = [], [], 0, set()
    for ref in references:
        if not isinstance(ref, dict) or set(ref) != {"role", "path", "binding"} or ref["role"] not in ("reference", "uv", "mask"):
            raise ComfyError("Invalid image specification")
        pair = ref["binding"]
        if (not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(x, str) for x in pair)
                or tuple(pair) in seen or ref["role"] in seen or pair in selected["prompt_inputs"] or pair in selected["seed_inputs"]):
            raise ComfyError("Duplicate or conflicting image binding")
        seen.update((tuple(pair), ref["role"]))
        node = workflow.get(pair[0], {})
        if node.get("class_type") != "LoadImage" or pair[1] != "image" or not isinstance(node.get("inputs", {}).get("image"), str):
            raise ComfyError("Only explicit LoadImage.image literals can be changed")
        source = Path(ref["path"])
        if source.is_symlink():
            raise ComfyError("Use a regular PNG source")
        data, _ = read_png(source)
        total += len(data)
        if total > 64*1024*1024:
            raise ComfyError("Reference batch exceeds 64 MiB")
        sha = hashlib.sha256(data).hexdigest(); filename = "cn_"+sha+".png"
        node["inputs"]["image"] = filename
        entries.append({"role": ref["role"], "binding": pair, "file": filename, "sha256": sha})
        staged.append((filename, data))
    # Reserve output before writing inputs. Existing bytes are verified, never overwritten.
    output.mkdir(parents=True, exist_ok=False)
    for filename, data in staged:
        destination = safe_path(root, filename)
        try:
            with destination.open("xb") as stream:
                stream.write(data)
        except FileExistsError:
            if read_png(destination)[0] != data:
                raise ComfyError("Input filename already contains different bytes")
    selected.update(workflow="workflow.json", workflow_sha256=workflow_digest(workflow), reference_inputs=entries)
    derived = {"schema": "cryptonyan.comfy-profiles/1", "endpoint": endpoint, "input_root": str(root.resolve()), "profiles": [selected]}
    write_json(output / "workflow.json", workflow)
    write_json(output / "profiles.json", derived)
    load_catalog(output / "profiles.json")
    return output / "profiles.json"


def main(argv=None):
    p = argparse.ArgumentParser(description="Prepare a reference-aware profile for the existing texture MCP service")
    p.add_argument("catalog", type=Path); p.add_argument("profile"); p.add_argument("references", type=Path)
    p.add_argument("--input-root", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    from .animation_doctor import read_json
    print(prepare(args.catalog, args.profile, read_json(args.references), args.input_root, args.output))


if __name__ == "__main__":
    main()
