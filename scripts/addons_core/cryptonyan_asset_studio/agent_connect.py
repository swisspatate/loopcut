# SPDX-License-Identifier: GPL-3.0-or-later
"""Local connection setup for external MCP clients; no account or client-config edits.

The UX is inspired by Mixar's public MCP guide. This implementation reuses our
mission server and ComfyUI adapter and has no dependency on Mixar's services.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SCHEMA = "cryptonyan.agent-connection/1"
CLIENTS = ("claude", "codex")
PATH_FIELDS = ("python", "workspace", "asset_root", "blender", "comfy_profiles", "game_project")
LAUNCHER = Path(__file__).with_name("mcp_launcher.py").resolve()


def validate_config(value):
    if (not isinstance(value, dict) or set(value) != {"schema", "executor", *PATH_FIELDS}
            or value["schema"] != SCHEMA or value["executor"] not in ("mock", "blender")):
        raise ValueError("Invalid connection profile schema or executor")
    for field in PATH_FIELDS:
        item = value[field]
        optional = field in ("blender", "comfy_profiles", "game_project")
        if not isinstance(item, str) or len(item) > 4096 or any(ord(c) < 32 for c in item):
            raise ValueError("Connection paths must be bounded strings without control characters")
        if not item and optional:
            continue
        if not item or not Path(item).is_absolute():
            raise ValueError("Connection paths must be absolute paths on this machine")
    if value["executor"] == "blender" and not value["blender"]:
        raise ValueError("Select a Blender executable for the Blender executor")
    return dict(value)


def load_config(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError("Invalid or oversized connection profile")
    return validate_config(json.loads(path.read_text(encoding="utf-8-sig")))


def save_config(path, config, *, replace=False):
    """Only overwrite our own schema when explicitly asked; never a client config."""
    config = validate_config(config)
    path = Path(path).absolute()
    if path.is_symlink():
        raise ValueError("Connection profile must not be a symbolic link")
    if path.exists():
        if not replace:
            raise ValueError("Connection profile already exists; use --replace to update it")
        load_config(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    if not replace:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(data)
    else:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".connection-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return path


def client_workspace(config, client):
    if client not in CLIENTS:
        raise ValueError("Unknown MCP client")
    # A stdio connection owns its queue. Different clients must not share its lock.
    from .storage import safe_path
    return safe_path(Path(config["workspace"]), "mcp-" + client)


def validate_paths(config):
    """Filesystem/config checks only. Does not instantiate a queue or an executor."""
    validate_config(config)
    python = Path(config["python"])
    if not python.is_file() or python.suffix.lower() in (".bat", ".cmd", ".ps1", ".sh"):
        raise ValueError("Select a standalone Python 3.11+ executable, not a shell wrapper")
    if os.name != "nt" and not os.access(python, os.X_OK):
        raise ValueError("Selected Python is not executable")
    assets, workspace = Path(config["asset_root"]).resolve(), Path(config["workspace"]).resolve()
    if not assets.is_dir():
        raise ValueError("Asset root must be an existing directory")
    if workspace.is_relative_to(assets) or assets.is_relative_to(workspace):
        raise ValueError("Workspace and asset root must be separate directories")
    for client in CLIENTS:
        client_workspace(config, client)
    ancestor = workspace
    while not ancestor.exists():
        ancestor = ancestor.parent
    if not ancestor.is_dir() or not os.access(ancestor, os.W_OK):
        raise ValueError("Workspace needs an existing writable parent directory")
    if config["executor"] == "blender":
        blender = Path(config["blender"])
        if (not blender.is_file() or blender.suffix.lower() in (".bat", ".cmd", ".ps1", ".sh")
                or os.name != "nt" and not os.access(blender, os.X_OK)):
            raise ValueError("Select an existing executable Blender binary")
    if config["game_project"]:
        from .game_project import GameProject
        project = GameProject(config["game_project"])
        if workspace.is_relative_to(project.root) or project.root.is_relative_to(workspace):
            raise ValueError("Workspace and game project must be separate directories")
    if config["comfy_profiles"]:
        from .comfy_profiles import load_catalog
        load_catalog(config["comfy_profiles"])


def launch_spec(config_path, client, *, diagnostic=False):
    config_path = Path(config_path).resolve()
    config = load_config(config_path)
    client_workspace(config, client)  # Validate before formatting any arguments.
    args = ["-I", str(LAUNCHER), "--config", str(config_path), "--client", client]
    if diagnostic:
        args.append("--diagnostic")
    return {"command": config["python"], "args": args}


def export_client(config_path, client):
    spec = launch_spec(config_path, client)
    if client == "claude":
        return json.dumps({"mcpServers": {"cryptonyan": {"type": "stdio", **spec}}},
                          indent=2, ensure_ascii=False) + "\n"
    # JSON strings/arrays are also valid TOML basic strings/arrays for our paths.
    return ("[mcp_servers.cryptonyan]\n"
            + "command = " + json.dumps(spec["command"], ensure_ascii=False) + "\n"
            + "args = " + json.dumps(spec["args"], ensure_ascii=False) + "\n")


def server_args(config, client, *, workspace=None):
    root = Path(workspace) if workspace is not None else client_workspace(config, client)
    args = ["--workspace", str(root), "--asset-root", config["asset_root"],
            "--executor", config["executor"]]
    for field in ("blender", "comfy_profiles", "game_project"):
        if config[field]:
            args.extend(["--" + field.replace("_", "-"), config[field]])
    return args + ["serve"]


def probe_mcp(config_path, client, *, timeout=15):
    """Initialize/list/ping a fresh disposable server; never submit a mission.

    The real workspace is not opened: MissionBridge resumes queued work on startup.
    The child closes stdin at EOF and is killed on timeout by subprocess.run.
    stdout is spooled to disk and only a bounded result is read into memory.
    """
    from .mcp_stdio import PROTOCOL, tool_list
    config = load_config(config_path)
    validate_paths(config)
    spec = launch_spec(config_path, client, diagnostic=True)
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "cryptonyan-connection-check", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
    ]
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run([spec["command"], *spec["args"]],
                input=("\n".join(json.dumps(m) for m in messages) + "\n").encode(),
                stdout=output, stderr=subprocess.DEVNULL, timeout=timeout, shell=False)
        except subprocess.TimeoutExpired:
            raise ValueError("MCP probe timed out; check the Python executable") from None
        if result.returncode:
            raise ValueError("MCP startup failed; check Python 3.11+, paths and optional catalogs")
        output.seek(0)
        raw = output.read(262145)
    if len(raw) > 262144:
        raise ValueError("MCP probe response exceeded its byte limit")
    try:
        replies = [json.loads(line) for line in raw.splitlines()]
        if len(replies) != 3 or any(r.get("jsonrpc") != "2.0" for r in replies):
            raise ValueError()
        if [r["id"] for r in replies] != [1, 2, 3] or any("error" in r for r in replies):
            raise ValueError()
        if (replies[0]["result"]["protocolVersion"] != PROTOCOL
                or replies[0]["result"]["serverInfo"]["name"] != "cryptonyan-asset-studio"
                or replies[2]["result"] != {}):
            raise ValueError()
        found = replies[1]["result"]["tools"]
        expected = tool_list(bool(config["comfy_profiles"]), bool(config["game_project"]))
        if found != expected:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("MCP handshake or tool catalog did not match the local server") from None
    return {"status": "ready", "protocol": PROTOCOL, "tools": [t["name"] for t in found],
            "isolated_workspace": True, "missions_submitted": 0, "model_called": False,
            "client_application_verified": False}


def probe_comfy(config, *, transport=None):
    from .comfy_profiles import load_catalog
    from .comfyui_adapter import LocalHTTP
    if not config["comfy_profiles"]:
        return {"status": "not_configured"}
    endpoint, profiles = load_catalog(config["comfy_profiles"])
    http = transport if transport is not None else LocalHTTP(endpoint)
    try:
        value = json.loads(http("GET", "/system_stats", limit=65536, timeout=3))
        if (not isinstance(value, dict) or not isinstance(value.get("system"), dict)
                or not isinstance(value.get("devices"), list)):
            raise ValueError()
    except (ValueError, OSError, RuntimeError):
        raise ValueError("ComfyUI did not return valid system metadata; check its local address and startup") from None
    return {"status": "reachable", "profiles": sorted(profiles), "generation_submitted": False,
            "models_and_gpu_verified": False}


def diagnose(config_path, client="claude", *, mcp=False, comfy=False):
    checks = []
    try:
        config = load_config(config_path)
        validate_paths(config)
    except (ValueError, OSError, RuntimeError):
        # Do not echo raw catalog data, paths or subprocess errors to the panel.
        return {"schema": "cryptonyan.connection-report/1", "status": "blocked", "checks": [
            {"name": "configuration", "status": "blocked",
             "message": "Check absolute executable paths, separate workspace/assets/project, and approved ComfyUI catalog."}]}
    checks.append({"name": "configuration", "status": "ready", "executor": config["executor"]})
    for name, enabled, action in (
        ("mcp", mcp, lambda: probe_mcp(config_path, client)),
        ("comfyui", comfy, lambda: probe_comfy(config)),
    ):
        if not enabled:
            checks.append({"name": name, "status": "not_tested"})
            continue
        try:
            checks.append({"name": name, **action()})
        except (ValueError, OSError, RuntimeError):
            checks.append({"name": name, "status": "unavailable", "message":
                "Check Python 3.11+ and paths." if name == "mcp" else "Start local ComfyUI and check its catalog endpoint."})
    return {"schema": "cryptonyan.connection-report/1",
            "status": "blocked" if any(c["status"] in ("blocked", "unavailable") for c in checks) else "checked",
            "checks": checks, "client_application_verified": False,
            "blender_execution_verified": False, "unreal_execution_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare and diagnose local Claude/Codex MCP connections")
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init", help="Write our profile; never edit Claude/Codex settings")
    init.add_argument("config", type=Path)
    init.add_argument("--python", default=sys.executable)
    init.add_argument("--workspace", required=True)
    init.add_argument("--asset-root", required=True)
    init.add_argument("--executor", choices=("mock", "blender"), default="blender")
    init.add_argument("--blender", default="")
    init.add_argument("--comfy-profiles", default="")
    init.add_argument("--game-project", default="")
    init.add_argument("--replace", action="store_true")
    export = commands.add_parser("export", help="Print a JSON/TOML fragment for review and copy")
    export.add_argument("config", type=Path)
    export.add_argument("--client", choices=CLIENTS, required=True)
    check = commands.add_parser("check", help="Check paths; optional probes never generate assets")
    check.add_argument("config", type=Path)
    check.add_argument("--client", choices=CLIENTS, default="claude")
    check.add_argument("--probe-mcp", action="store_true")
    check.add_argument("--probe-comfy", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "init":
        config = {"schema": SCHEMA, "executor": args.executor}
        config.update({field: str(Path(getattr(args, field)).expanduser().resolve())
                       if getattr(args, field) else "" for field in PATH_FIELDS})
        validate_paths(config)
        save_config(args.config, config, replace=args.replace)
        print(json.dumps({"status": "saved", "config": str(args.config.resolve())}))
        return 0
    if args.action == "export":
        print(export_client(args.config, args.client), end="")
        return 0
    report = diagnose(args.config, args.client, mcp=args.probe_mcp, comfy=args.probe_comfy)
    print(json.dumps(report, indent=2))
    return 1 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError):
        print("Connection setup failed; check paths, profile schema and existing destination.", file=sys.stderr)
        raise SystemExit(2)
