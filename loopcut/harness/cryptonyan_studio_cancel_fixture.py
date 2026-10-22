# SPDX-License-Identifier: GPL-3.0-or-later
"""Deliberately long Blender fixture for real process cancellation tests."""
from pathlib import Path
import time
import bpy

bpy.ops.wm.save_as_mainfile(filepath=str(Path.cwd() / 'partial.blend'))
(Path.cwd() / 'blender-ready.txt').write_text(bpy.app.version_string, encoding='utf-8')
while True:
    time.sleep(0.1)
