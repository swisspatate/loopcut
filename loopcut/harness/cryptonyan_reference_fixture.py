# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual Blender UI registration and operator calls, without a graphical display."""
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
import cryptonyan_asset_studio as studio
from cryptonyan_asset_studio import reference_board, reference_ui


def main():
    folder, image, recipe = sys.argv[sys.argv.index("--") + 1:]
    root = Path(folder)
    before = [(o.name, tuple(o.location)) for o in bpy.context.scene.objects]
    studio.register()
    settings = bpy.context.window_manager.cryptonyan_references
    settings.folder = str(root / "ui-board")
    settings.board_id = "ui-board"
    settings.title = "Tableau de test"
    assert bpy.ops.cryptonyan.reference_action(action="CREATE") == {"FINISHED"}
    settings.image_file = image
    settings.reference_id = "front"
    assert bpy.ops.cryptonyan.reference_action(action="ADD") == {"FINISHED"}
    assert len(settings.items) == 1
    assert len(reference_ui._previews) == 1
    settings.notes = "Silhouette à conserver"
    assert bpy.ops.cryptonyan.reference_action(action="NOTES") == {"FINISHED"}
    settings.annotation_text = "Toit"
    assert bpy.ops.cryptonyan.reference_action(action="ANNOTATE") == {"FINISHED"}
    assert len(reference_board.load(settings.folder)["references"][0]["annotations"]) == 1
    settings.recipe_file = recipe
    assert bpy.ops.cryptonyan.reference_action(action="RECIPE") == {"FINISHED"}
    settings.output = str(root / "ui-bundle")
    assert bpy.ops.cryptonyan.reference_action(action="PREPARE") == {"FINISHED"}
    settings.review_file = str(root / "ui-review.html")
    assert bpy.ops.cryptonyan.reference_action(action="HTML") == {"FINISHED"}
    assert (root / "ui-review.html").is_file()
    assert (root / "ui-bundle/plan.json").is_file()
    assert not (root / "ui-bundle/candidate.blend").exists()
    assert before == [(o.name, tuple(o.location)) for o in bpy.context.scene.objects]
    studio.unregister()
    assert reference_ui._previews is None
    assert not hasattr(bpy.types.WindowManager, "cryptonyan_references")
    print("CRYPTONYAN_REFERENCE_ASSERTIONS_PASSED")


main()
