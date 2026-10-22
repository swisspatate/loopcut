# SPDX-License-Identifier: GPL-3.0-or-later
import base64
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
from cryptonyan_asset_studio import reference_board as board
from cryptonyan_asset_studio import agent_connect
from cryptonyan_asset_studio.image_workshop import load_bundle, run
from cryptonyan_asset_studio.mcp_stdio import MCPServer, tool_list
from cryptonyan_asset_studio.storage import OwnerLock, digest, write_json
from test_cryptonyan_materials import png
from test_cryptonyan_image_workshop import recipe
from test_cryptonyan_agent_connect import LocalPeer


class Fixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reference board é-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.library = self.root / "library"
        self.folder = self.library / "temple"
        self.image = self.root / "reference.png"
        self.image.write_bytes(png(width=64, height=64))
        self.game = self.root / "game"
        self.game.mkdir()
        (self.game / "Test.uproject").write_text('{"FileVersion":3}')
        (self.game / "Content").mkdir()
        self.asset = self.game / "Content/Temple.uasset"
        self.asset.write_bytes(b"existing game asset")
        board.create(self.folder, "temple", "Temple de glace", self.game)

    def add(self):
        return board.add(self.folder, 0, "front", self.image, "Face avant")

    def attached(self):
        self.add()
        board.link(self.folder, 1, "front", "Content/Temple.uasset")
        return board.edit(self.folder, 2, "front", recipe=recipe())


class BoardTests(Fixture, unittest.TestCase):
    def test_snapshot_survives_original_change_and_context_is_explicit(self):
        original = self.image.read_bytes()
        self.add()
        self.image.write_bytes(png((30, 50, 70)))
        result = board.context(self.folder)
        self.assertEqual(Path(result["image_paths"]["front"]).read_bytes(), original)
        self.assertTrue(result["visual_interpretation_required"])
        self.assertFalse(result["generation_submitted"])
        self.assertEqual(result["targets"], {"front": "not_linked"})

    def test_notes_and_annotations_roundtrip_and_preserve_inputs(self):
        self.add()
        regions = [{"id": "roof", "text": "Conserver la silhouette", "rect": [.1, .2, .5, .3]}]
        original = copy.deepcopy(regions)
        value = board.edit(self.folder, 1, "front", notes="Glace\nAccents cyan", regions=regions)
        self.assertEqual(value["revision"], 2)
        self.assertEqual(board.load(self.folder)["references"][0]["annotations"], regions)
        self.assertEqual(regions, original)

    def test_stale_revision_never_publishes_image_or_metadata(self):
        self.add()
        before = digest(self.folder / "board.json")
        files = set((self.folder / "images").iterdir())
        self.image.write_bytes(png((10, 20, 30)))
        with self.assertRaisesRegex(ValueError, "reload"):
            board.add(self.folder, 0, "side", self.image, "Side")
        self.assertEqual(digest(self.folder / "board.json"), before)
        self.assertEqual(set((self.folder / "images").iterdir()), files)

    def test_concurrent_writer_is_rejected(self):
        self.add()
        before = digest(self.folder / "board.json")
        lock = OwnerLock(self.folder / "edit.lock")
        try:
            with self.assertRaises(RuntimeError):
                board.edit(self.folder, 1, "front", notes="concurrent")
        finally:
            lock.close()
        self.assertEqual(digest(self.folder / "board.json"), before)

    def test_invalid_annotation_bounds_duplicates_nan_and_limits(self):
        valid = {"id": "zone", "text": "Roof", "rect": [0, 0, 1, 1]}
        cases = [[{**valid, "rect": r}] for r in ([0, 0, 0, 1], [.7, 0, .5, 1], [0, -1, .2, .3],
                 [True, 0, 1, 1], [float("nan"), 0, 1, 1], [0, 0, 1])]
        cases += [[valid, valid], [valid] * 17, [{**valid, "text": ""}], [{**valid, "id": "../escape"}]]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                board.annotations(value)

    def test_invalid_image_and_budget_leave_board_unchanged(self):
        before = digest(self.folder / "board.json")
        self.image.write_bytes(b"not a png")
        with self.assertRaises(ValueError):
            self.add()
        self.image.write_bytes(png())
        with patch.object(board, "MAX_TOTAL", 1), self.assertRaises(ValueError):
            self.add()
        self.assertEqual(digest(self.folder / "board.json"), before)

    def test_reference_count_and_duplicate_ids(self):
        self.add()
        with self.assertRaises(ValueError):
            board.add(self.folder, 1, "front", self.image, "Duplicate")
        for i in range(1, 16):
            board.add(self.folder, i, "ref-" + str(i), self.image, "Reference")
        with self.assertRaises(ValueError):
            board.add(self.folder, 16, "extra", self.image, "Too many")

    def test_snapshot_tampering_rejected_before_preview_or_image_delivery(self):
        value = self.add()
        path = self.folder / value["references"][0]["image"]["file"]
        path.write_bytes(png((1, 2, 3)))
        with self.assertRaisesRegex(ValueError, "changed"):
            board.load(self.folder)
        with self.assertRaises(ValueError):
            board.ReferenceService(self.library).image("temple", "front")

    def test_metadata_path_tampering_and_unknown_fields(self):
        value = self.add()
        for mutation in (lambda v: v.update(extra=True),
                         lambda v: v["references"][0]["image"].update(file="../reference.png"),
                         lambda v: v.update(references=v["references"] * 2)):
            changed = copy.deepcopy(value)
            mutation(changed)
            write_json(self.folder / "board.json", changed)
            with self.assertRaises(ValueError):
                board.load(self.folder)

    def test_link_fingerprints_existing_asset_without_writing_game(self):
        before = digest(self.asset)
        self.add()
        value = board.link(self.folder, 1, "front", "Content/Temple.uasset")
        self.assertEqual(value["references"][0]["target"]["sha256"], before)
        self.assertEqual(board.context(self.folder)["targets"], {"front": "unchanged"})
        self.assertEqual(digest(self.asset), before)

    def test_lfs_pointer_and_traversal_rejected(self):
        self.add()
        self.asset.write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:test")
        with self.assertRaises(ValueError):
            board.link(self.folder, 1, "front", "Content/Temple.uasset")
        with self.assertRaises(ValueError):
            board.link(self.folder, 1, "front", "../reference.png")

    def test_changed_target_blocks_handoff_until_explicit_rebind(self):
        self.attached()
        self.asset.write_bytes(b"new asset revision")
        self.assertEqual(board.context(self.folder)["targets"], {"front": "changed"})
        output = self.root / "bundle"
        with self.assertRaisesRegex(ValueError, "changed"):
            board.prepare_reference(self.folder, 3, "front", output)
        self.assertFalse(output.exists())
        board.link(self.folder, 3, "front", "Content/Temple.uasset")
        board.prepare_reference(self.folder, 4, "front", output)
        self.assertEqual(load_bundle(output)["recipe"], recipe())

    def test_project_descriptor_change_and_missing_target_are_reported(self):
        self.attached()
        (self.game / "Test.uproject").write_text('{"FileVersion":3,"Description":"changed"}')
        self.assertEqual(board.context(self.folder)["targets"], {"front": "unavailable"})
        with self.assertRaises(ValueError):
            board.prepare_reference(self.folder, 3, "front", self.root / "bundle")

    def test_handoff_records_board_revision_and_never_launches_worker(self):
        self.attached()
        output = self.root / "bundle"
        before = digest(self.asset)
        with patch.object(subprocess, "Popen", side_effect=AssertionError("No process expected")):
            trace = board.prepare_reference(self.folder, 3, "front", output)
        self.assertEqual(trace["plan_identity"], load_bundle(output)["identity"])
        self.assertEqual(trace["board_identity"], board.identity(board.load(self.folder)))
        self.assertEqual(trace["reference"]["target"]["sha256"], before)
        self.assertFalse(trace["generation_submitted"])
        self.assertEqual(digest(self.asset), before)
        with self.assertRaises(FileExistsError):
            board.prepare_reference(self.folder, 3, "front", output)

    def test_prepare_requires_recipe_revision_and_separate_destination(self):
        self.add()
        with self.assertRaises(ValueError):
            board.prepare_reference(self.folder, 1, "front", self.root / "missing-recipe")
        board.edit(self.folder, 1, "front", recipe=recipe())
        for revision, output in ((1, self.root / "stale"), (2, self.folder / "inside"), (2, self.game / "generated")):
            with self.subTest(output=output), self.assertRaises(ValueError):
                board.prepare_reference(self.folder, revision, "front", output)
            self.assertFalse(output.exists())

    def test_html_escapes_notes_and_labels_and_embeds_rectangles(self):
        self.add()
        board.edit(self.folder, 1, "front", notes='<script>alert("bad")</script>',
                   regions=[{"id": "roof", "text": "<b>Roof</b>", "rect": [.1, .2, .5, .3]}])
        path = self.root / "review.html"
        board.export_html(self.folder, path)
        html = path.read_text(encoding="utf-8")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn('viewBox="0 0 1000 1000"', html)
        self.assertIn('<rect x="100.0" y="200.0" width="500.0" height="300.0"', html)
        self.assertNotIn('src="http', html)
        with self.assertRaises(FileExistsError):
            board.export_html(self.folder, path)
        with self.assertRaises(ValueError):
            board.export_html(self.folder, self.game / "review.html")

    def test_board_cannot_be_created_inside_game_or_replace_directory(self):
        with self.assertRaises(ValueError):
            board.create(self.game / "board", "bad", "Bad", self.game)
        with self.assertRaises(FileExistsError):
            board.create(self.folder, "other", "Other")

    def test_read_only_service_bounds_paths_and_returns_verified_image(self):
        self.add()
        service = board.ReferenceService(self.library)
        self.assertEqual(service.boards()["boards"][0]["board_id"], "temple")
        image = service.image("temple", "front")
        self.assertEqual(base64.b64decode(image["data"]), self.image.read_bytes())
        self.assertEqual(image["mimeType"], "image/png")
        with self.assertRaises(ValueError):
            service.read("../game")
        with self.assertRaises(ValueError):
            service.image("temple", "missing")
        self.assertEqual(board.ReferenceService(self.root / "absent").boards(), {"boards": []})

    def test_mcp_returns_native_image_content_and_keeps_tools_opt_in(self):
        self.add()
        self.assertNotIn("reference_image", [t["name"] for t in tool_list()])
        server = MCPServer(None, references=board.ReferenceService(self.library))
        server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "reference_image", "arguments": {"board_id": "temple", "reference_id": "front"}}})
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["content"][0]["type"], "image")
        response = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "reference_read", "arguments": {"board_id": "../secret"}}})
        self.assertTrue(response["result"]["isError"])

    def test_existing_connection_profiles_migrate_and_new_profile_exposes_boards(self):
        self.add()
        config = {"schema": agent_connect.SCHEMA, "executor": "mock", "python": sys.executable,
            "asset_root": str(self.game / "Content"), "workspace": str(self.root / "jobs"),
            "blender": "", "game_project": "", "comfy_profiles": ""}
        self.assertEqual(agent_connect.validate_config(config)["reference_root"], "")
        config["reference_root"] = str(self.library)
        path = self.root / "connection.json"
        agent_connect.save_config(path, config)
        diagnostic = agent_connect.probe_mcp(path, "claude")
        self.assertIn("reference_image", diagnostic["tools"])
        before = digest(self.folder / "board.json")
        peer = LocalPeer(path, "claude")
        self.addCleanup(peer.close)
        peer.call("initialize")
        value = peer.tool("reference_read", {"board_id": "temple"})
        self.assertEqual(value["board"]["revision"], 1)
        response = peer.call("tools/call", {"name": "reference_image", "arguments": {
            "board_id": "temple", "reference_id": "front"}})
        self.assertEqual(base64.b64decode(response["content"][0]["data"]), self.image.read_bytes())
        self.assertEqual(digest(self.folder / "board.json"), before)

    def test_cli_create_add_read_and_html(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        prefix = [sys.executable, "-m", "cryptonyan_asset_studio.reference_board"]
        folder = self.library / "cli"
        for args in (["create", str(folder), "--id", "cli", "--title", "CLI board"],
                     ["add", str(folder), "--revision", "0", "--reference", "front", "--image", str(self.image), "--title", "Front"],
                     ["read", str(folder)], ["html", str(folder), "--output", str(self.root / "cli.html")]):
            result = subprocess.run(prefix + args, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)


BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


@unittest.skipUnless(BLENDER, "Real Blender unavailable")
class BlenderTests(Fixture, unittest.TestCase):
    def test_sidebar_actual_rna_previews_annotations_and_prepare(self):
        path = self.root / "recipe.json"
        path.write_text(json.dumps(recipe()), encoding="utf-8")
        result = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
            "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_reference_fixture.py"),
            "--", str(self.root), str(self.image), str(path)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CRYPTONYAN_REFERENCE_ASSERTIONS_PASSED", result.stdout)

    def test_board_to_actual_blender_candidate_preserves_game_asset(self):
        self.attached()
        before = digest(self.asset)
        bundle, output = self.root / "bundle", self.root / "rendered"
        trace = board.prepare_reference(self.folder, 3, "front", bundle)
        receipt = run(bundle, output, BLENDER, timeout=90)
        self.assertEqual(receipt["plan_identity"], trace["plan_identity"])
        self.assertEqual(receipt["status"], "candidate_created_review_required")
        self.assertTrue((output / "candidate.blend").is_file())
        self.assertTrue((output / "comparison.html").is_file())
        self.assertEqual(digest(self.asset), before)


if __name__ == "__main__":
    unittest.main()
