# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in local extension of the existing MCP launcher; native UI dispatch only.

The normal server and its schemas stay unchanged when launched without this entry point.
"""
import argparse
import json
from pathlib import Path
import sys


def server_type(queue):
    from cryptonyan_asset_studio.mcp_stdio import MCPServer
    from loopcut.brief_queue import INSTRUCTIONS, native_tools

    class NativeMCPServer(MCPServer):
        def handle(self, message):
            if (isinstance(message, dict) and message.get('jsonrpc') == '2.0' and 'id' in message
                    and message.get('method') == 'tools/call' and self.initialized):
                params = message.get('params', {})
                if isinstance(params, dict) and params.get('name') in {t['name'] for t in native_tools()}:
                    try:
                        value = queue.call(params['name'], params.get('arguments', {}))
                        result = dict(content=[dict(type='text', text=json.dumps(value))], isError=False)
                    except (ValueError, OSError, RuntimeError) as exc:
                        result = dict(content=[dict(type='text', text=str(exc))], isError=True)
                    return dict(jsonrpc='2.0', id=message['id'], result=result)
            response = super().handle(message)
            if response and 'result' in response:
                if message.get('method') == 'initialize':
                    response['result']['instructions'] += INSTRUCTIONS
                    response['result']['serverInfo']['version'] += '+native-briefs.1'
                elif message.get('method') == 'tools/list':
                    response['result']['tools'] += native_tools()
            return response
    return NativeMCPServer


def main(argv=None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from cryptonyan_asset_studio import mcp_stdio
    from cryptonyan_asset_studio.mcp_launcher import main as original
    from loopcut.brief_queue import BriefQueue
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--bridge-config', required=True)
    args, remaining = parser.parse_known_args(argv)
    queue = BriefQueue(args.bridge_config)
    selected = server_type(queue)
    desktop_config = queue.config_path.parent / 'desktop-relay.json'
    if desktop_config.exists():
        from cryptonyan_asset_studio.desktop_relay import DesktopRelay, extend_server
        selected = extend_server(selected, DesktopRelay(desktop_config))
    mcp_stdio.MCPServer = selected
    return original(remaining)


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception:
        print('Native Loopcut MCP startup failed; inspect bridge/profile paths.', file=sys.stderr)
        raise SystemExit(2)
