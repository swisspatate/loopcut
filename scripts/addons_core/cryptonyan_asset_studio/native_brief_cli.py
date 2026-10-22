# SPDX-License-Identifier: GPL-3.0-or-later
"""Same native queue as MCP; fallback for already-open clients with cached tools."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from loopcut.brief_queue import BriefQueue
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge-config',required=True)
    parser.add_argument('action',choices=('status','submit','get','cancel'))
    parser.add_argument('--request-id')
    parser.add_argument('--brief-file')
    parser.add_argument('--expected-session')
    parser.add_argument('--expected-scene',default='')
    args=parser.parse_args(argv);queue=BriefQueue(args.bridge_config)
    if args.action=='status':value=queue.status()
    elif args.action=='get':value=queue.get(args.request_id)
    elif args.action=='cancel':value=queue.cancel(args.request_id)
    else:
        path=Path(args.brief_file).resolve()
        if not queue.scene_allowed(str(path)) or path.stat().st_size>64000:raise ValueError('Brief file must be bounded and inside workshop')
        value=queue.submit(args.request_id,path.read_text(encoding='utf-8-sig'),args.expected_session,args.expected_scene)
    print(json.dumps(value,indent=2,ensure_ascii=False));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'failed','error':str(exc)}),file=sys.stderr);raise SystemExit(2)
