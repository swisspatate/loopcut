# SPDX-License-Identifier: GPL-3.0-or-later
"""Qualify mapped StaticMesh bounds before delegating to the existing Director adapter."""
import argparse
import json
from pathlib import Path

from .animation_doctor import number
from .creative_director import make_plan
from .modular_levels import load_bundle,director
from .reference_board import _separate
from .storage import digest,write_json
from .unreal_material_variants import _runtime,_path,_kind
from .unreal_director import execute


def review(bundle,output,*,apply=False,unreal_module=None):
    if unreal_module is None:
        import unreal as unreal_module
    u=unreal_module
    if type(apply) is not bool:raise ValueError('Choose an explicit boolean apply flag')
    version,game=_runtime(u)
    bundle,output=Path(bundle).resolve(),Path(output).resolve()
    _separate(bundle,output);_separate(game.root,output)
    level=load_bundle(bundle);spec=director(level)
    if spec is None:raise ValueError('Map every used module to an existing Unreal StaticMesh before review')
    plan=make_plan(spec,game.root)
    checked=[]
    by_id={m['id']:m for m in level['catalog']['modules']}
    for key in sorted({p['module'] for p in level['placements']}):
        path=by_id[key]['unreal_mesh'];mesh=u.load_asset(path)
        if _path(mesh)!=path or _kind(mesh)!='StaticMesh':raise ValueError('Mapped module is missing, redirected or not a StaticMesh')
        bounds=mesh.get_bounding_box()
        actual=[[number(getattr(c,axis),-1e8,1e8)/100 for axis in ('x','y','z')] for c in (bounds.min,bounds.max)]
        expected=level['modules'][key]['bounds_unreal_m']
        if any(abs(a-b)>.001 for x,y in zip(actual,expected) for a,b in zip(x,y)):
            raise ValueError('Unreal module bounds differ from the pinned GLB; fix the export, pivot or mapping')
        checked.append({'module':key,'asset':path,'bounds_m':actual})
    output.mkdir(parents=True,exist_ok=False)
    receipt={'schema':'cryptonyan.modular-unreal-review/1','plan_identity':level['identity'],'unreal_version':version,
             'status':'running','bounds_checked':checked,'engine_validated':False,'controller_validated':False,'navmesh_validated':False}
    try:
        write_json(output/'director-plan.json',plan)
        # Existing adapter verifies classes, source hashes, an empty review map and rollback.
        result=execute(output/'director-plan.json',output/'director-receipt.json',apply=apply,unreal_module=u)
        receipt.update(status=result['status'],files={name:{'sha256':digest(output/name),'bytes':(output/name).stat().st_size}
                       for name in ('director-plan.json','director-receipt.json')})
        if load_bundle(bundle)!=level:raise ValueError('Modular bundle changed during Unreal review')
        return receipt
    except BaseException:
        receipt['status']='failed';raise
    finally:write_json(output/'review.json',receipt)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--apply',action='store_true')
    a=parser.parse_args(argv);result=review(a.bundle,a.output,apply=a.apply)
    print(json.dumps(result,indent=2));return 1 if result['status']=='failed' else 0


if __name__=='__main__':raise SystemExit(main())
