# SPDX-License-Identifier: GPL-3.0-or-later
"""Scripted wire peer only. Never calls a model; uses verified app-server field names."""
import json
from pathlib import Path
import sys

scenario = sys.argv[1]
record_path = Path(sys.argv[2])


def send(message):
    print(json.dumps(message), flush=True)


def reply(message, result):
    send({"jsonrpc": "2.0", "id": message["id"], "result": result})


def tool(identity="tool-1", arguments=None, name="cryptonyan_asset_doctor", thread="thread-1"):
    send({"jsonrpc": "2.0", "id": identity, "method": "item/tool/call", "params": {
        "threadId": thread, "turnId": "turn-1", "callId": identity, "tool": name,
        "arguments": arguments if arguments is not None else {}}})


def complete(status="completed"):
    send({"jsonrpc": "2.0", "method": "turn/completed",
          "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": status}}})


for raw in sys.stdin:
    message = json.loads(raw)
    with record_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(message) + "\n")
    method = message.get("method")
    if method == "initialize":
        if scenario == "exit":
            break
        if scenario == "malformed":
            print("not json", flush=True)
            continue
        if scenario == "oversized":
            print("x" * (1024 * 1024 + 1), flush=True)
            continue
        if scenario == "rpc_error":
            send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -1, "message": "SECRET_RAW_ERROR"}})
        else:
            reply(message, {"userAgent": "codex-cli/0.163.0"})
    elif method == "account/read":
        reply(message, {"account": None if scenario == "no_auth" else {
            "type": "apiKey" if scenario == "api_key" else "chatgpt", "email": "PRIVATE_ACCOUNT_EMAIL"},
            "requiresOpenaiAuth": True})
    elif method == "thread/start":
        reply(message, {"thread": {"id": "thread-1"}, "sandbox": {
            "type": "dangerFullAccess" if scenario == "permissions" else "readOnly"}, "approvalPolicy": "never"})
    elif method == "turn/start":
        if scenario == "early":
            tool()
        reply(message, {"turn": {"id": "turn-1"}})
        if scenario in ("no_audit", "failed"):
            complete("failed" if scenario == "failed" else "completed")
        elif scenario == "wait":
            continue
        elif scenario == "approval":
            send({"jsonrpc": "2.0", "id": "approval", "method": "item/commandExecution/requestApproval", "params": {}})
        elif scenario == "wrong_thread":
            tool(thread="unrelated")
        elif scenario == "alter_scope":
            tool(arguments={"inputs": ["../../source.blend"]})
        elif scenario == "unknown_tool":
            tool(name="run_python")
        elif scenario != "early":
            tool()
    elif method == "turn/interrupt":
        reply(message, {})
        complete("interrupted")
    elif message.get("id") == "approval":
        tool()
    elif message.get("id") == "tool-1":
        if scenario == "repeat":
            tool("tool-2")
        elif scenario in ("alter_scope", "unknown_tool"):
            tool("tool-2")
        else:
            complete()
    elif message.get("id") == "tool-2":
        complete()
