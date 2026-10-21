# SPDX-License-Identifier: GPL-3.0-or-later
"""Unreal -ExecutePythonScript entry point; planning also works with plain Python."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/addons_core"))
from cryptonyan_asset_studio.unreal_world import main

if __name__ == "__main__":
    raise SystemExit(main())
