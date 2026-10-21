# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender --background --factory-startup --disable-autoexec --python ... -- ..."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/addons_core"))
from cryptonyan_asset_studio.blender_materials import apply_material_copy

parser = argparse.ArgumentParser(description="Apply a validated PBR bundle to a new Blender copy")
parser.add_argument("--source", required=True, type=Path)
parser.add_argument("--bundle", required=True, type=Path)
parser.add_argument("--object", required=True)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
print(json.dumps(apply_material_copy(args.source, args.bundle, args.object, args.output)))
