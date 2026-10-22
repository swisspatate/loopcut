# SPDX-License-Identifier: GPL-3.0-or-later
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio import visual_versions as versions, reference_board as boards
from cryptonyan_asset_studio.image_workshop import prepare, run
from cryptonyan_asset_studio.storage import digest, write_json, OwnerLock
from loopcut import glb
from test_cryptonyan_image_workshop import recipe, source_glb
from test_cryptonyan_materials import png


def attempt(root, name="attempt", value=None, color=(10, 20, 30)):
    output = root / name
    output.mkdir()
    image = root / (name + ".png")
    image.write_bytes(png(color, width=64, height=64))
    plan = prepare(image, value or recipe(), output / "inputs")
    (output / "candidate.glb").write_bytes(source_glb())
    (output / "candidate.blend").write_bytes(b"fixture, never executed")
    (output / "render.png").write_bytes(png(width=64, height=64))
    summary = glb.summary(glb.parse(source_glb())[0])
    write_json(output / "geometry.json", {"plan_identity": plan["identity"], "triangles": summary["tris"], "objects": summary["nodes"]})
    write_json(output / "asset-doctor.json", {"passed": False})
    (output / "comparison.html").write_text("fixture")
    receipt = {"schema": "cryptonyan.image-attempt/1", "plan_identity": plan["identity"],
               "status": "candidate_created_review_required", "visual_quality_validated": False, "engine_validated": False,
               "artifacts": {f: {"sha256": digest(output / f), "bytes": (output / f).stat().st_size} for f in versions.ARTIFACTS}}
    write_json(output / "operation.json", receipt)
    return output


class VersionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="versions é ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.folder = self.root / "history"
        self.attempt = attempt(self.root)
        self.game = self.root / "game"
        self.game.mkdir(); (self.game / "Test.uproject").write_text('{"FileVersion":3}')
        (self.game / "Content").mkdir(); (self.game / "Content/Temple.uasset").write_bytes(b"original")
        versions.create(self.folder, "temple", "Temple", self.game)

    def archive(self):
        return versions.archive(self.folder, 0, "v01", self.attempt, "First")

    def test_independent_snapshot_survives_deleted_attempt_and_restores_exact_bytes(self):
        self.archive()
        original = versions.inspect_attempt(self.attempt)
        shutil.rmtree(self.attempt)
        self.assertEqual(versions.read_version(self.folder, "v01")["attempt"], original)
        result = versions.restore(self.folder, "v01", self.root / "restored")
        self.assertFalse(result["scene_opened"])
        self.assertEqual(versions.inspect_attempt(self.root / "restored"), original)

    def test_stale_revision_and_duplicate_do_not_publish(self):
        self.archive()
        for rev, key in ((0, "v02"), (1, "v01")):
            with self.assertRaises(ValueError):
                versions.archive(self.folder, rev, key, self.attempt, "bad")
        self.assertEqual(len(versions.load(self.folder)["versions"]), 1)
        self.assertFalse((self.folder / "versions/v02").exists())

    def test_single_writer_lock(self):
        lock = OwnerLock(self.folder / "edit.lock")
        try:
            with self.assertRaises(RuntimeError): self.archive()
        finally: lock.close()
        self.assertEqual(versions.load(self.folder)["revision"], 0)

    def test_partial_failed_or_claimed_validated_attempt_rejected(self):
        path = self.attempt / "operation.json"
        original = json.loads(path.read_text())
        for update in ({"status": "running"}, {"status": "failed"}, {"engine_validated": True}, {"artifacts": {}}):
            write_json(path, {**original, **update})
            with self.assertRaises(ValueError): self.archive()
        self.assertEqual(versions.load(self.folder)["revision"], 0)

    def test_artifact_and_input_tampering(self):
        for filename in ("render.png", "inputs/reference.png", "candidate.blend"):
            path = self.attempt / filename; original = path.read_bytes()
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError): self.archive()
            path.write_bytes(original)

    def test_archive_tampering_blocks_selection_and_restoration(self):
        self.archive()
        (self.folder / "versions/v01/candidate.blend").write_bytes(b"tampered")
        with self.assertRaises(ValueError): versions.select(self.folder, 1, "v01")
        with self.assertRaises(ValueError): versions.restore(self.folder, "v01", self.root / "restore")
        self.assertFalse((self.root / "restore").exists())
        self.assertIsNone(versions.load(self.folder)["selected"])

    def test_snapshot_metadata_tamper(self):
        self.archive()
        p = self.folder / "versions/v01/snapshot.json"
        value = json.loads(p.read_text()); value["board"] = {"invented": True}; write_json(p, value)
        with self.assertRaisesRegex(ValueError, "identity"): versions.read_version(self.folder, "v01")

    def test_selection_is_explicit_and_never_changes_game(self):
        self.archive()
        before = digest(self.game / "Content/Temple.uasset")
        self.assertIsNone(versions.load(self.folder)["selected"])
        value = versions.select(self.folder, 1, "v01")
        self.assertEqual((value["selected"], value["revision"]), ("v01", 2))
        self.assertEqual(digest(self.game / "Content/Temple.uasset"), before)
        with self.assertRaises(ValueError): versions.select(self.folder, 1, "v01")

    def test_restore_existing_and_project_or_history_destinations_rejected(self):
        self.archive()
        existing = self.root / "existing"; existing.mkdir()
        for output in (existing, self.game / "Content/new", self.folder / "new", self.root):
            with self.assertRaises((ValueError, FileExistsError)):
                versions.restore(self.folder, "v01", output)
        self.assertEqual(list(existing.iterdir()), [])

    def test_compare_identical_and_changed_camera_reference_with_escaped_recipe(self):
        self.archive()
        same = versions.compare(self.folder, "v01", "v01", self.root / "same.html")
        self.assertTrue(same["same_camera"] and same["same_reference"])
        value = recipe(); value["camera"]["lens_mm"] = 80; value["intent"] = '<script>alert(1)</script>'
        other = attempt(self.root, "other", value, (200, 30, 50))
        versions.archive(self.folder, 1, "v02", other, "Other")
        result = versions.compare(self.folder, "v01", "v02", self.root / "review.html")
        self.assertFalse(result["same_camera"] or result["same_reference"])
        self.assertIn("camera", result["changed_recipe_fields"])
        page = (self.root / "review.html").read_text(encoding="utf-8")
        self.assertIn("non équivalente", page); self.assertNotIn("<script>", page)
        self.assertIn("data:image/png;base64,", page)
        with self.assertRaises(FileExistsError): versions.compare(self.folder, "v01", "v02", self.root / "review.html")

    def test_budget_limits_do_not_publish(self):
        for key in ("MAX_ATTEMPT", "MAX_TOTAL", "MAX_VERSIONS"):
            with patch.object(versions, key, 1), self.assertRaises(ValueError):
                if key == "MAX_VERSIONS":
                    self.archive()
                    versions.archive(self.folder, 1, "v02", self.attempt, "Second")
                else: self.archive()

    def test_copy_failure_does_not_publish_and_releases_lock(self):
        with patch.object(versions, "_copy", side_effect=OSError("disk full")), self.assertRaises(OSError): self.archive()
        self.assertEqual(versions.load(self.folder)["revision"], 0)
        self.assertFalse((self.folder / "versions/v01").exists())
        self.archive()

    def test_restore_failure_cleans_only_new_owned_folder(self):
        self.archive()
        with patch.object(versions, "_copy", side_effect=OSError("disk full")), self.assertRaises(OSError):
            versions.restore(self.folder, "v01", self.root / "restore")
        self.assertFalse((self.root / "restore").exists())
        versions.read_version(self.folder, "v01")

    def test_index_failure_leaves_unpublished_version_not_visible(self):
        original = versions.write_json
        def fail(path, value):
            if Path(path).name == "history.json": raise OSError("disk full")
            original(path, value)
        with patch.object(versions, "write_json", side_effect=fail), self.assertRaises(OSError): self.archive()
        self.assertEqual(versions.load(self.folder)["versions"], [])
        with self.assertRaises(ValueError): versions.read_version(self.folder, "v01")
        with self.assertRaises(ValueError): self.archive()

    def test_traversal_and_symlink_rejected(self):
        for key in ("../other", "A", "a/b"):
            with self.assertRaises(ValueError): versions.archive(self.folder, 0, key, self.attempt, "bad")
        path = self.attempt / "candidate.blend"; path.unlink()
        try: path.symlink_to(self.game / "Content/Temple.uasset")
        except OSError: self.skipTest("OS symlink privilege unavailable")
        with self.assertRaises(ValueError): self.archive()

    def test_bound_board_provenance_and_changed_target_rejection(self):
        board = self.root / "board"
        boards.create(board, "board", "Board", self.game)
        boards.add(board, 0, "front", self.root / "attempt.png", "Front")
        boards.edit(board, 1, "front", recipe=recipe())
        boards.link(board, 2, "front", "Content/Temple.uasset")
        versions.archive(self.folder, 0, "v01", self.attempt, "Bound", board, "front")
        self.assertEqual(versions.read_version(self.folder, "v01")["board"]["revision"], 3)
        (self.game / "Content/Temple.uasset").write_bytes(b"changed")
        with self.assertRaises(ValueError): versions.archive(self.folder, 1, "v02", self.attempt, "Stale", board, "front")

    def test_cli_roundtrip(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        prefix = [sys.executable, "-m", "cryptonyan_asset_studio.visual_versions"]
        for args in (["list", str(self.folder)], ["archive", str(self.folder), "--revision", "0", "--version", "v01", "--attempt", str(self.attempt), "--label", "CLI"],
                     ["check", str(self.folder), "--version", "v01"], ["select", str(self.folder), "--revision", "1", "--version", "v01"],
                     ["restore", str(self.folder), "--version", "v01", "--output", str(self.root / "restored")]):
            result = subprocess.run(prefix + args, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)


BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


@unittest.skipUnless(BLENDER, "Real Blender unavailable")
class BlenderTests(unittest.TestCase):
    def test_actual_blender_build_archive_restore_and_sidebar(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "ref.png"; image.write_bytes(png(width=64, height=64))
            prepare(image, recipe(), root / "bundle")
            run(root / "bundle", root / "attempt", BLENDER, timeout=90)
            result = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
                "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_versions_fixture.py"),
                "--", str(root)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CRYPTONYAN_VERSIONS_ASSERTIONS_PASSED", result.stdout)
            self.assertEqual(versions.inspect_attempt(root / "restored"), versions.inspect_attempt(root / "attempt"))


if __name__ == "__main__": unittest.main()
