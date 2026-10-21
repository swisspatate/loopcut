# SPDX-License-Identifier: GPL-3.0-or-later
"""Unreal Python entry point; also usable as a pure-Python bundle dry run.

In the Unreal Python console, import run_review_import from the package for an
interactive editor session. This script supports -ExecutePythonScript usage locally.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "addons_core"))
from cryptonyan_asset_studio.unreal_review import run_review_import


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a bundle, optionally import in Unreal 5.8")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="Explicitly import into a new Unreal review folder")
    args = parser.parse_args(argv)
    result = run_review_import(args.manifest, args.report, apply=args.apply)
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError):
        print("Invalid package or receipt path; no import started.", file=sys.stderr)
        raise SystemExit(2)
