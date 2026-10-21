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


def tool_list():
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
    return result


class MCPServer:
    def __init__(self, bridge):
        self.bridge = bridge
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
            result = {"tools": tool_list()}
        elif method == "tools/call":
            try:
                name, args = params.get("name"), params.get("arguments", {})
                spec = next((t for t in tool_list() if t["name"] == name), None)
                if spec is None or not isinstance(args, dict) or set(args) != set(spec["inputSchema"]["required"]):
                    return error(-32602, "Unknown tool or invalid arguments")
                if name == "mission_submit":
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


def serve(bridge, source, destination):
    server = MCPServer(bridge)
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
