# SPDX-License-Identifier: GPL-3.0-or-later
"""Use the same approved TextureService from native Loopcut shell tools; no extra AI."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from loopcut.brief_queue import BriefQueue
    from cryptonyan_asset_studio.comfy_profiles import TextureService
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge-config', required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('action', choices=('profiles', 'preflight', 'submit', 'status', 'collect', 'inspect'))
    parser.add_argument('--profile')
    parser.add_argument('--request-id')
    parser.add_argument('--prompt')
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args(argv)
    queue = BriefQueue(args.bridge_config)
    workspace = Path(args.workspace).resolve()
    if workspace == queue.work or not queue.scene_allowed(str(workspace)):
        raise ValueError('Comfy job workspace must be below the workshop, outside protected roots')
    with TextureService(queue.config['comfy_profiles'], workspace, handle_root=workspace.parent) as service:
        if args.action == 'profiles': result = service.catalog()
        elif args.action in ('preflight', 'submit'):
            result = service.preflight(args.profile, args.prompt, args.seed)
            if args.action == 'submit':
                if result.get('status') in ('blocked', 'unavailable'): raise ValueError('Comfy profile preflight blocked')
                result = service.submit(args.profile, args.prompt, args.seed, args.request_id)
        elif args.action == 'status': result = service.status(args.request_id)
        elif args.action == 'collect': result = service.collect(args.request_id)
        else: result = service.inspect(args.request_id)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'failed','error':str(exc)}), file=sys.stderr)
        raise SystemExit(2)
