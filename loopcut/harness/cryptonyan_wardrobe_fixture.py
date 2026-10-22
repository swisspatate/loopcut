# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural existing rig and two already skinned garments; no game assets."""
import json
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/addons_core'))
args = sys.argv[sys.argv.index('--')+1:]

if args[0] == 'create':
    bpy.ops.wm.read_factory_settings(use_empty=True)
    data = bpy.data.armatures.new('ExistingSkeleton')
    rig = bpy.data.objects.new('ExistingRig', data); bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig; rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    root = data.edit_bones.new('Origin'); root.head, root.tail = (0, 0, 0), (0, 0, 1)
    tip = data.edit_bones.new('Tip'); tip.head, tip.tail, tip.parent = (0, 0, 1), (0, 0, 2), root
    bpy.ops.object.mode_set(mode='OBJECT')
    for action, axis, end in (('Bend', 1, -.4), ('Safe', 0, .2)):
        rig.animation_data_create(); rig.animation_data.action = None
        rig.pose.bones['Tip'].location = (0, 0, 0)
        for frame, value in ((1, 0), (3, end)):
            rig.pose.bones['Tip'].location[axis] = value
            rig.pose.bones['Tip'].keyframe_insert('location', index=axis, frame=frame)
        rig.animation_data.action.name = action
        rig.animation_data.action.use_fake_user = True
    bpy.context.scene.frame_set(1)
    if '--units' in args: bpy.context.scene.unit_settings.scale_length = .25
    image = bpy.data.images.new('PackedTexture', width=2, height=2)
    image.pixels = [1, 0, 0, 1]*4; image.pack(); image.filepath = '//packed-texture.png'
    image.use_fake_user = True
    bpy.ops.mesh.primitive_cube_add()
    body = bpy.context.object; body.name = 'Body'
    body.vertex_groups.new(name='Origin').add(list(range(8)), 1, 'REPLACE')
    body.modifiers.new('Skin', 'ARMATURE').object = rig
    if '--open' in args:
        import bmesh
        bm = bmesh.new(); bm.from_mesh(body.data); bm.faces.ensure_lookup_table()
        bm.faces.remove(bm.faces[0]); bm.to_mesh(body.data); bm.free()
    for name, bone, z in (('Shirt', 'Tip', 1.1), ('Cape', 'Origin', 1.2)):
        mesh = bpy.data.meshes.new(name+'Mesh')
        size = 2 if '--cross' in args and name == 'Shirt' else .5
        if '--cross' in args and name == 'Shirt': z = 0
        mesh.from_pydata([(-size, -size, z), (size, -size, z), (size, size, z), (-size, size, z)], [], [(0, 1, 2, 3)])
        obj = bpy.data.objects.new(name, mesh); bpy.context.scene.collection.objects.link(obj)
        obj.vertex_groups.new(name=bone).add(list(range(4)), 1, 'REPLACE')
        obj.vertex_groups.new(name='PaintMask').add([0], .25, 'REPLACE')
        obj.modifiers.new('Skin', 'ARMATURE').object = rig
        obj.parent = rig
        if '--shape' in args and name == 'Shirt':
            obj.shape_key_add(name='Basis'); key = obj.shape_key_add(name='Style')
            for v in key.data: v.co.z += .05
            key.value = .5
        if '--wrong-rig' in args and name == 'Shirt': obj.modifiers[0].object = None
    bpy.ops.wm.save_as_mainfile(filepath=args[1], check_existing=False)
elif args[0] == 'ui':
    import cryptonyan_asset_studio as studio
    from cryptonyan_asset_studio.storage import digest
    from cryptonyan_asset_studio.rig_worker import sample
    root = Path(args[1]); source = root / 'source.blend'
    bpy.ops.wm.open_mainfile(filepath=str(source), use_scripts=False)
    spec = json.loads((root / 'spec.json').read_text())
    settings = dict(armature='ExistingRig', meshes=['Body', 'Shirt', 'Cape'])
    weights = sample(settings); source_hash = digest(source)
    geometry = {o.name: [tuple(v.co) for v in o.data.vertices] for o in bpy.data.objects if o.type == 'MESH'}
    action = bpy.data.objects['ExistingRig'].animation_data.action.name
    frame = bpy.context.scene.frame_current
    studio.register(); studio.register()
    s = bpy.context.window_manager.cryptonyan_wardrobe
    s.source = str(source); s.specification = str(root / 'spec.json'); s.output = str(root / 'review')
    assert bpy.ops.cryptonyan.wardrobe_review() == {'FINISHED'}
    assert source_hash == digest(source) and sample(settings) == weights
    assert bpy.context.scene.frame_current == frame
    assert bpy.data.objects['ExistingRig'].animation_data.action.name == action
    studio.unregister(); studio.unregister()
    assert not hasattr(bpy.types.WindowManager, 'cryptonyan_wardrobe')
    report = json.loads((root / 'review/wardrobe.json').read_text())
    for clip in report['clips']:
        bpy.ops.wm.open_mainfile(filepath=str(root / 'review' / clip['review_file']), use_scripts=False)
        assert sample(settings) == weights
        assert geometry == {o.name: [tuple(v.co) for v in o.data.vertices] for o in bpy.data.objects if o.type == 'MESH'}
        rig = bpy.data.objects['ExistingRig']
        assert rig.animation_data.action.name == clip['capture']['action'] and not rig.animation_data.use_nla
        assert bpy.context.scene.frame_current == clip['review_frame']
        assert bpy.context.scene['cryptonyan_wardrobe_window'] == clip['index']
        if clip['capture']['action'] == 'Bend':
            assert bpy.context.scene.frame_current == 3
            assert any(m.name.startswith('CN_WR_') and m.frame == 3 for m in bpy.context.scene.timeline_markers)
            assert bpy.context.view_layer.objects.active.name == 'Shirt'
        assert bpy.data.objects['Shirt'].data.shape_keys.key_blocks['Style'].value == .5
        assert bpy.data.images['PackedTexture'].packed_file is not None
    print('CRYPTONYAN_WARDROBE_ASSERTIONS_PASSED')
else:
    raise ValueError('Unknown fixture mode')
