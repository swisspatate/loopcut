# SPDX-License-Identifier: GPL-3.0-or-later
"""Real headless integration; explicit skips when no Blender is available."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "addons_core"))
from cryptonyan_asset_studio.bridge import MissionBridge
from cryptonyan_asset_studio.executors import BlenderExecutor
from cryptonyan_asset_studio.storage import digest, safe_path

BLENDER = os.environ.get("LOOPCUT_BLENDER") or shutil.which("blender")


@unittest.skipUnless(BLENDER, "Blender executable unavailable; set LOOPCUT_BLENDER to enable headless tests")
class BlenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.scene = self.assets / "fixture.blend"
        self.run_blender("create", self.scene)

    def run_blender(self, mode, path):
        completed = subprocess.run([BLENDER, "--background", "--factory-startup", "--disable-autoexec",
            "--threads", "1", "--python-exit-code", "1", "--python", str(ROOT / "loopcut/harness/cryptonyan_fixture.py"),
            "--", mode, str(path)], capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("CRYPTONYAN_BLENDER_ASSERTIONS_PASSED", completed.stdout)

    def test_direct_audit_guards_and_geometry_preservation(self):
        before = digest(self.scene)
        self.run_blender("verify", self.scene)
        self.assertEqual(digest(self.scene), before)

    def test_headless_bridge_dry_run_and_review_copy(self):
        before = digest(self.scene)
        with MissionBridge(self.root / "jobs", self.assets, BlenderExecutor(BLENDER)) as bridge:
            dry = bridge.submit({"inputs": ["fixture.blend"]})
            final = bridge.wait(dry["id"], 60)
            self.assertEqual(final["state"], "succeeded", final)
            self.assertEqual(len(final["artifacts"]), 1)
            self.assertTrue(bridge.result(dry["id"])["quality"]["reports"][0]["dry_run"])
            fixed = bridge.revise(dry["id"], {"inputs": ["fixture.blend"], "constraints": {"repair_copy": True}})
            final = bridge.wait(fixed["id"], 60)
            self.assertEqual(final["state"], "succeeded", final)
            self.assertEqual(len(final["artifacts"]), 2)
            result = bridge.result(fixed["id"])
            self.assertFalse(result["quality"]["reports"][0]["dry_run"])
            repaired = next(a for a in final["artifacts"] if a["path"].endswith(".blend"))
            self.run_blender("verify_saved", safe_path(bridge.store.folder(fixed["id"]), repaired["path"]))
        self.assertEqual(digest(self.scene), before)

    def test_scripted_codex_dispatches_real_blender(self):
        # The app-server peer is scripted; the delegated Blender worker is real.
        from test_cryptonyan_codex import ScriptedCodex
        before = digest(self.scene)
        executor = ScriptedCodex("tool", self.root / "wire.jsonl", BlenderExecutor(BLENDER))
        with MissionBridge(self.root / "jobs", self.assets, executor) as bridge:
            task = bridge.submit({"inputs": ["fixture.blend"]})
            final = bridge.wait(task["id"], 60)
            self.assertEqual(final["state"], "succeeded", final)
            result = bridge.result(task["id"])
            self.assertEqual(result["quality"]["reports"][0]["source"], "blender")
            self.assertTrue(any(a["path"].endswith("codex-dispatch.json") for a in final["artifacts"]))
        self.assertEqual(digest(self.scene), before)


if __name__ == "__main__":
    unittest.main()
