# SPDX-License-Identifier: GPL-3.0-or-later
"""Run in a factory-startup Blender; exercise actual RNA/operator registration."""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
import cryptonyan_asset_studio as studio
from cryptonyan_asset_studio import agent_connect
from cryptonyan_asset_studio import connection_ui


def main():
    folder, python = sys.argv[sys.argv.index("--") + 1:]
    root = Path(folder)
    assets = root / "assets"
    assets.mkdir()
    before = [(obj.name, tuple(obj.location), obj.type) for obj in bpy.context.scene.objects]
    assert not hasattr(bpy.types.WindowManager, "cryptonyan_connection")
    studio.register()
    studio.register()  # Explicit activation is idempotent.
    settings = bpy.context.window_manager.cryptonyan_connection
    settings.config_path = str(root / "connection.json")
    settings.python = python
    settings.asset_root = str(assets)
    settings.workspace = str(root / "work")
    settings.blender = bpy.app.binary_path
    assert bpy.ops.cryptonyan.connection_save() == {"FINISHED"}
    settings.client = "claude"
    assert bpy.ops.cryptonyan.connection_copy() == {"FINISHED"}
    # Background Blender has no OS clipboard. Exercise the actual operator above
    # and validate its generated payload separately; interactive clipboard is local QA.
    fragment = json.loads(agent_connect.export_client(root / "connection.json", "claude"))
    assert Path(fragment["mcpServers"]["cryptonyan"]["command"]).resolve() == Path(python).resolve()
    settings.workspace = str(root / "edited")
    assert bpy.ops.cryptonyan.connection_load() == {"FINISHED"}
    assert settings.workspace == str(root / "work")
    settings.client = "codex"
    assert bpy.ops.cryptonyan.connection_copy() == {"FINISHED"}
    assert "[mcp_servers.cryptonyan]" in agent_connect.export_client(root / "connection.json", "codex")
    report = agent_connect.diagnose(root / "connection.json", "codex", mcp=True)
    assert report["status"] == "checked", report
    assert report["checks"][1]["status"] == "ready", report
    assert not (root / "work").exists()
    # Exercise modal result delivery with actual RNA/timers, advancing events
    # explicitly because a background Blender has no interactive event loop.
    assert bpy.ops.cryptonyan.connection_check() == {"RUNNING_MODAL"}
    operator = next(iter(connection_ui._jobs))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if operator.modal(bpy.context, SimpleNamespace(type="TIMER")) == {"FINISHED"}:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("Modal diagnostic did not finish")
    assert json.loads(settings.report_json)["status"] == "checked"
    assert not connection_ui._jobs
    assert bpy.ops.cryptonyan.connection_check() == {"RUNNING_MODAL"}
    operator = next(iter(connection_ui._jobs))
    settings.workspace = str(root / "edited-during-check")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if operator.modal(bpy.context, SimpleNamespace(type="TIMER")) == {"FINISHED"}:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("Stale modal diagnostic did not finish")
    assert settings.report_json == "", "Stale result must not mark new settings as checked"
    assert not connection_ui._jobs
    assert before == [(obj.name, tuple(obj.location), obj.type) for obj in bpy.context.scene.objects]
    studio.unregister()
    studio.unregister()
    assert not hasattr(bpy.types.WindowManager, "cryptonyan_connection")
    print("CRYPTONYAN_CONNECTION_ASSERTIONS_PASSED")


main()
