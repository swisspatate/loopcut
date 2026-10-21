# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only existing Unreal project discovery and asset-bound texture requests.

No Unreal package parsing, scripts, hooks, editor RPC or asset writes happen here.
The private TextureService workspace owns all generated data and durable bindings.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from .comfy_profiles import _identifier, _read, MAX_REQUESTS
from .storage import digest, safe_path, write_json

ASSET_ROOTS = ("Content", "SourceAssets")
EXTENSIONS = {".uasset", ".umap", ".blend", ".fbx", ".glb", ".gltf", ".png", ".tga", ".exr"}
TEXTURE_TARGETS = {".uasset", ".blend", ".fbx", ".glb"}
MAX_ENTRIES = 100000
MAX_TARGET_BYTES = 512 * 1024 * 1024
LFS_HEADER = b"version https://git-lfs.github.com/spec/v1"


class GameProject:
    def __init__(self, root, textures=None):
        self.root = Path(root).resolve(strict=True)
        self.textures = textures
        projects = list(self.root.glob("*.uproject"))
        if len(projects) != 1:
            raise ValueError("Select a project directory containing exactly one .uproject")
        self.descriptor = safe_path(self.root, projects[0].name)
        self.config = _read(self.descriptor)
        if not isinstance(self.config, dict) or self.config.get("FileVersion") != 3:
            raise ValueError("Unsupported Unreal project descriptor")
        if textures is not None:
            workspace = Path(textures.root).resolve()
            if workspace.is_relative_to(self.root) or self.root.is_relative_to(workspace):
                raise ValueError("Texture workspace and game project must be separate directories")
            self.bindings = safe_path(workspace, "asset-bindings")
            self.bindings.mkdir(exist_ok=True)

    def _project_identity(self):
        # Bound to this checkout and descriptor, never exposed as a machine path.
        path = safe_path(self.root, self.descriptor.name)
        _read(path)  # Recheck size and symlinks before hashing a changed descriptor.
        return hashlib.sha256((str(self.root) + "\n" + digest(path)).encode()).hexdigest()

    def _assets(self):
        found, visited = [], 0
        for folder in ASSET_ROOTS:
            start = safe_path(self.root, folder)
            if not start.exists():
                continue
            pending = [start]
            while pending:
                current = pending.pop()
                with os.scandir(current) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > MAX_ENTRIES:
                            raise ValueError("Project inventory exceeds the 100000-entry scan budget")
                        if entry.is_symlink():
                            continue
                        relative = Path(entry.path).relative_to(self.root).as_posix()
                        path = safe_path(self.root, relative)
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(path)
                        elif entry.is_file(follow_symlinks=False) and path.suffix.lower() in EXTENSIONS:
                            found.append(relative)
        return sorted(found)

    def _asset(self, relative):
        path = safe_path(self.root, relative)
        if relative.split("/")[0] not in ASSET_ROOTS or path.suffix.lower() not in EXTENSIONS or not path.is_file():
            raise ValueError("Select an existing supported file under Content or SourceAssets")
        with path.open("rb") as stream:
            lfs = stream.read(256).startswith(LFS_HEADER)
        package = "/Game/" + relative[len("Content/"):].rsplit(".", 1)[0] if relative.startswith("Content/") and path.suffix.lower() in {".uasset", ".umap"} else None
        return {"path": relative, "bytes": path.stat().st_size, "git_lfs_pointer": lfs,
                "unreal_package": package, "asset_class": None,
                "dependencies_inspected": False, "rig_inspected": False}

    def inventory(self, query="", offset=0, limit=100):
        if (not isinstance(query, str) or len(query) > 256 or "\x00" in query
                or type(offset) is not int or offset < 0
                or type(limit) is not int or not 1 <= limit <= 200):
            raise ValueError("Use a query up to 256 characters, nonnegative offset and limit 1-200")
        assets = self._assets()
        matches = [p for p in assets if query.casefold() in p.casefold()]
        return {"schema": "cryptonyan.project-inventory/1", "project": self.descriptor.name,
                "engine_association": self.config.get("EngineAssociation"),
                "scope": list(ASSET_ROOTS), "total": len(assets), "matched": len(matches),
                "assets": [self._asset(p) for p in matches[offset:offset + limit]],
                "next_offset": offset + limit if offset + limit < len(matches) else None,
                "editor_inspected": False}

    def profiles(self):
        """Native source catalog is metadata, never silently converted/executed."""
        path = safe_path(self.root, "Pipeline/comfy_profiles.json")
        native = []
        if path.exists():
            catalog = _read(path)
            profiles = catalog.get("profiles") if isinstance(catalog, dict) else None
            if not isinstance(profiles, dict) or len(profiles) > 128:
                raise ValueError("Unsupported native project profile catalog")
            for name, spec in profiles.items():
                if not isinstance(name, str) or not isinstance(spec, dict):
                    raise ValueError("Invalid native project profile")
                # Do not expose arbitrary workflow contents, file paths or model configuration.
                native.append({"id": name[:128], "workflow": str(spec.get("workflow", ""))[:128],
                               "purpose": str(spec.get("purpose", ""))[:1024],
                               "executable_by_texture_bridge": False})
        return {"native_project_profiles": native,
                "texture_profiles": self.textures.catalog()["profiles"] if self.textures else [],
                "native_catalog_auto_converted": False}

    def _snapshot(self, target):
        asset = self._asset(target)
        path = safe_path(self.root, target)
        if path.suffix.lower() not in TEXTURE_TARGETS:
            raise ValueError("Texture requests target .uasset, .blend, .fbx or .glb files")
        if asset["git_lfs_pointer"]:
            raise ValueError("Download Git LFS content locally before binding this asset")
        if not 0 < asset["bytes"] <= MAX_TARGET_BYTES:
            raise ValueError("Target must contain 1 byte to 512 MiB")
        before = path.stat()
        sha = digest(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ValueError("Target changed while being fingerprinted")
        return {"path": target, "sha256": sha, "bytes": after.st_size}

    def _receipt(self, request_id):
        if self.textures is None:
            raise ValueError("Configure reviewed texture profiles before submitting asset requests")
        return safe_path(self.bindings, _identifier(request_id) + ".json")

    def _verify(self, record):
        if record["project_identity"] != self._project_identity():
            raise ValueError("Request belongs to a different project or changed project descriptor")
        if record["source"] != self._snapshot(record["request"]["target"]):
            raise ValueError("Target changed since submission; review the candidate before using it")

    def texture_submit(self, request_id, target, surface, profile, prompt, seed):
        receipt = self._receipt(request_id)
        if not isinstance(surface, str) or not surface.strip() or len(surface) > 256 or "\x00" in surface:
            raise ValueError("Describe the intended object/material slot in 1-256 characters")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4096 or "\x00" in prompt:
            raise ValueError("Prompt must contain 1-4096 characters without NUL")
        _identifier(profile)
        if type(seed) is not int or not 0 <= seed < 2**64:
            raise ValueError("Seed must be an unsigned 64-bit integer")
        request = dict(request_id=request_id, target=target, surface=surface, profile=profile, prompt=prompt, seed=seed)
        if receipt.exists():
            record = _read(receipt)
            if record["request"] != request:
                raise ValueError("Asset request ID already used with different parameters")
            self._verify(record)
        else:
            if profile not in self.textures.profiles:
                raise ValueError("Select an executable texture profile, not a native 3D project profile")
            if self.textures._folder(request_id).exists():
                raise ValueError("Request ID already belongs to an unbound texture request")
            if sum(1 for p in self.bindings.iterdir() if not p.name.endswith(".candidate.json")) >= MAX_REQUESTS:
                raise ValueError("Asset binding capacity reached")
            record = {"schema": "cryptonyan.asset-texture-request/1", "request": request,
                      "project_identity": self._project_identity(), "source": self._snapshot(target)}
            # Persist BEFORE the underlying POST; restart reuses TextureService idempotency.
            write_json(receipt, record)
        result = self.textures.submit(request_id=request_id, profile=profile, prompt=prompt, seed=seed)
        return {**result, "target": record["source"], "surface": surface,
                "surface_verified": False, "applied_to_game": False}

    def texture_collect(self, request_id):
        record = _read(self._receipt(request_id))
        if record["request"]["request_id"] != request_id:
            raise ValueError("Asset request receipt identity mismatch")
        self._verify(record)
        result = self.textures.collect(request_id)
        self._verify(record)  # A collection can block while the user edits the source.
        candidate = {"schema": "cryptonyan.asset-texture-candidate/1", "target": record["source"],
                     "surface": record["request"]["surface"], "texture": result,
                     "project_identity": record["project_identity"], "surface_verified": False,
                     "applied_to_game": False, "requires_local_visual_review": True}
        output = safe_path(self.bindings, request_id + ".candidate.json")
        write_json(output, candidate)
        return {**candidate, "candidate_manifest": str(output)}

    def material_plan(self, request_id, inspection, slot, bindings, variant_id):
        """Prepare a local editor plan from an owned candidate and editor inspection."""
        import re
        from .unreal_material_variants import plan_variant
        record = _read(self._receipt(request_id))
        if record["request"]["request_id"] != request_id:
            raise ValueError("Asset request receipt identity mismatch")
        self._verify(record)
        if not isinstance(variant_id, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", variant_id):
            raise ValueError("Variant ID needs 1-64 alphanumeric or underscore characters")
        source = safe_path(safe_path(self.textures.root, "inspections"), inspection)
        candidate = safe_path(self.bindings, request_id + ".candidate.json")
        plan = plan_variant(source, candidate, slot, bindings, "/Game/CryptoNyan/MaterialVariants/" + variant_id)
        if (plan["source"] != record["source"] or plan["project_identity"] != record["project_identity"]
                or Path(plan["project_root"]).resolve() != self.root):
            raise ValueError("Material candidate does not match the owned request")
        output = safe_path(self.bindings, request_id + "." + variant_id + ".plan.json")
        if output.exists():
            if _read(output, 16 * 1024 * 1024) != plan:
                raise ValueError("Variant plan ID already used with different parameters")
        else:
            with output.open("x", encoding="utf-8") as stream:
                json.dump(plan, stream, indent=2, allow_nan=False)
        return {"plan_file": str(output), "plan": plan, "editor_execution_required": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect an existing Unreal project without launching the editor")
    parser.add_argument("project", type=Path)
    parser.add_argument("--query", default="")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--profiles", action="store_true")
    args = parser.parse_args(argv)
    project = GameProject(args.project)
    print(json.dumps(project.profiles() if args.profiles else project.inventory(args.query, args.offset, args.limit), indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError):
        raise SystemExit("Project inspection failed; check project path, file availability and catalog format")
