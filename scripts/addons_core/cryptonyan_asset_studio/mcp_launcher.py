# SPDX-License-Identifier: GPL-3.0-or-later
"""Absolute-file entry point: works with Python -I, without cwd/PYTHONPATH setup."""
import argparse
from pathlib import Path
import sys
import tempfile


def main(argv=None):
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11+ is required")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from cryptonyan_asset_studio.agent_connect import CLIENTS, load_config, server_args, validate_paths
    from cryptonyan_asset_studio.__main__ import main as serve_main
    parser = argparse.ArgumentParser(description="CryptoNyan local MCP launcher")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--client", required=True, choices=CLIENTS)
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    validate_paths(config)
    if args.diagnostic:
        with tempfile.TemporaryDirectory(prefix="cryptonyan-mcp-check-") as temporary:
            return serve_main(server_args(config, args.client, workspace=temporary))
    return serve_main(server_args(config, args.client))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # stdout belongs exclusively to JSON-RPC, stderr never includes profile data.
        print("CryptoNyan MCP startup failed; run agent_connect check on this profile.", file=sys.stderr)
        raise SystemExit(2)
