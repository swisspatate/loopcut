# SPDX-License-Identifier: GPL-3.0-or-later
"""Real RNA/operator checks; candidate scenes are never loaded into the live scene."""
from pathlib import Path
import sys
import bpy
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
import cryptonyan_asset_studio as studio
from cryptonyan_asset_studio import visual_versions as versions
root = Path(sys.argv[sys.argv.index("--") + 1])
before = [(o.name, tuple(o.location)) for o in bpy.context.scene.objects]
studio.register()
studio.register()
s = bpy.context.window_manager.cryptonyan_versions
s.folder = str(root / "history")
assert bpy.ops.cryptonyan.version_action(action="CREATE") == {"FINISHED"}
s.attempt = str(root / "attempt")
assert bpy.ops.cryptonyan.version_action(action="ARCHIVE") == {"FINISHED"}
s.version_id = "v02"
assert bpy.ops.cryptonyan.version_action(action="ARCHIVE") == {"FINISHED"}
s.version_id = "v01"
assert bpy.ops.cryptonyan.version_action(action="SELECT") == {"FINISHED"}
s.review = str(root / "review.html")
assert bpy.ops.cryptonyan.version_action(action="COMPARE") == {"FINISHED"}
s.output = str(root / "restored")
assert bpy.ops.cryptonyan.version_action(action="RESTORE") == {"FINISHED"}
assert versions.load(root / "history")["selected"] == "v01"
assert before == [(o.name, tuple(o.location)) for o in bpy.context.scene.objects]
studio.unregister()
studio.unregister()
assert not hasattr(bpy.types.WindowManager, "cryptonyan_versions")
print("CRYPTONYAN_VERSIONS_ASSERTIONS_PASSED")
