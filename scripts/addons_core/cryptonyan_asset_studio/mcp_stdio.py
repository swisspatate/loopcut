# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicitly launched MCP stdio transport (2024-11-05); no listening network socket."""
import json

from . import __version__

PROTOCOL = "2024-11-05"
MISSION_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["inputs"],
    "properties": {
        "schema": {"type": "string", "enum": ["cryptonyan.mission/1"]},
        "type": {"type": "string", "enum": ["asset_doctor", "asset_publish"]},
        "inputs": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 32, "uniqueItems": True},
        "target_assets": {"type": "array", "items": {"type": "string"}, "maxItems": 128, "uniqueItems": True},
        "constraints": {"type": "object", "additionalProperties": False, "properties": {
            "timeout_seconds": {"type": "number", "minimum": 0.05, "maximum": 3600},
            "max_attempts": {"type": "integer", "minimum": 1, "maximum": 3},
            "repair_copy": {"type": "boolean", "default": False}}},
        "success_criteria": {"type": "object", "additionalProperties": False, "properties": {
            "max_triangles": {"type": "integer", "minimum": 0, "maximum": 10000000},
            "allow_warnings": {"type": "boolean", "default": True}}},
    },
}


def tool_list(textures=False):
    descriptions = {
        "submit": "Queue an audit or static mesh publication mission; publish requires one .blend and one explicit target. Returns a task ID.",
        "query": "Read durable task state, timestamps, errors and artifact hashes.",
        "cancel": "Cancel a queued or running task; running cancellation is asynchronous.",
        "revise": "Create a new task from a terminal task and a complete replacement mission.",
        "result": "Retrieve a completed quality report after verifying artifact hashes.",
    }
    result = []
    for name, description in descriptions.items():
        properties = {}
        if name != "submit":
            properties["task_id"] = {"type": "string", "pattern": "^[a-f0-9]{32}$"}
        if name in ("submit", "revise"):
            properties["mission"] = MISSION_SCHEMA
        result.append({"name": "mission_" + name, "description": description,
                       "inputSchema": {"type": "object", "additionalProperties": False,
                                       "properties": properties, "required": list(properties)}})
    if textures:
        identity = {"type": "string", "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"}
        for name, description, properties in (
            ("profiles", "List operator-configured ComfyUI workflows/models and supported texture channels. Only prompt and seed are adjustable.", {}),
            ("jobs", "List durable texture requests for recovery; does not poll the GPU service.", {}),
            ("submit", "Generate a texture with a configured profile. Choose a unique request_id; reuse exactly the same ID/parameters after a lost response. Never automatically resubmit uncertain jobs with a new ID.",
             {"request_id": identity, "profile": identity, "prompt": {"type": "string", "minLength": 1, "maxLength": 4096},
              "seed": {"type": "integer", "minimum": 0, "maximum": 2**64 - 1}}),
            ("status", "Poll one owned ComfyUI request. Unknown history does not prove failure or cancellation.", {"request_id": identity}),
            ("collect", "Collect successful PNG outputs as a verified Material Doctor bundle. Returns manifest/receipt paths; does not apply a material to a scene.", {"request_id": identity}),
            ("cancel", "Request deletion of one queued prompt. Running cancellation requires ComfyUI; never globally interrupts other work.", {"request_id": identity}),
        ):
            result.append({"name": "texture_" + name, "description": description,
                           "inputSchema": {"type": "object", "additionalProperties": False,
                                           "properties": properties, "required": list(properties)}})
    return result


class MCPServer:
    def __init__(self, bridge, textures=None):
        self.bridge = bridge
        self.textures = textures
        self.initialized = False

    def handle(self, message):
        identity = message.get("id") if isinstance(message, dict) else None

        def error(code, text):
            return {"jsonrpc": "2.0", "id": identity, "error": {"code": code, "message": text}}

        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return error(-32600, "Invalid Request")
        if "id" not in message:
            return None  # Notifications never receive responses.
        method, params = message["method"], message.get("params", {})
        if not isinstance(params, dict):
            return error(-32602, "Invalid params")
        if method == "initialize":
            self.initialized = True
            result = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "cryptonyan-asset-studio", "version": __version__}}
        elif method == "ping":
            result = {}
        elif not self.initialized:
            return error(-32000, "Initialize the MCP session first")
        elif method == "tools/list":
            result = {"tools": tool_list(self.textures is not None)}
        elif method == "tools/call":
            try:
                name, args = params.get("name"), params.get("arguments", {})
                spec = next((t for t in tool_list(self.textures is not None) if t["name"] == name), None)
                if spec is None or not isinstance(args, dict) or set(args) != set(spec["inputSchema"]["required"]):
                    return error(-32602, "Unknown tool or invalid arguments")
                if name.startswith("texture_"):
                    action = name.removeprefix("texture_")
                    value = getattr(self.textures, "catalog" if action == "profiles" else action)(**args)
                elif name == "mission_submit":
                    value = self.bridge.submit(args["mission"])
                elif name == "mission_revise":
                    value = self.bridge.revise(args["task_id"], args["mission"])
                else:
                    value = getattr(self.bridge, name.removeprefix("mission_"))(args["task_id"])
                result = {"content": [{"type": "text", "text": json.dumps(value, allow_nan=False)}], "isError": False}
            except (ValueError, RuntimeError) as exc:
                # Public methods raise fixed validation messages without reflecting input values.
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            except Exception:
                result = {"content": [{"type": "text", "text": "Local service error; inspect workspace health."}], "isError": True}
        else:
            return error(-32601, "Method not found")
        return {"jsonrpc": "2.0", "id": identity, "result": result}


def serve(bridge, source, destination, textures=None):
    server = MCPServer(bridge, textures)
    while True:
        line = source.readline(65537)
        if not line:
            return
        if len(line) > 65536:
            raise ValueError("MCP message exceeds 64 KiB character limit")
        try:
            message = json.loads(line)
        except (ValueError, RecursionError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            response = server.handle(message)
        if response is not None:
            destination.write(json.dumps(response, allow_nan=False) + "\n")
            destination.flush()
