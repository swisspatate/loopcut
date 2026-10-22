# SPDX-License-Identifier: GPL-3.0-or-later
"""File-based camera programs and isolated Blender previews."""
import bpy
from bpy.props import PointerProperty, StringProperty
from . import camera_moves
from .animation_doctor import read_json
from .reference_ui import _path


class CryptoNyanCameraSettings(bpy.types.PropertyGroup):
    recipe: StringProperty(name="Mouvements caméra JSON",subtype="FILE_PATH")
    bundle: StringProperty(name="Nouvelle préparation",subtype="DIR_PATH")
    output: StringProperty(name="Nouveau dossier d'aperçu",subtype="DIR_PATH")
    blender: StringProperty(name="Blender (vide = courant)",subtype="FILE_PATH")
    status: StringProperty(options={"SKIP_SAVE"})


class CRYPTONYAN_OT_camera_action(bpy.types.Operator):
    bl_idname="cryptonyan.camera_action"
    bl_label="Mouvements caméra"
    action:StringProperty()

    def execute(self,context):
        s=context.window_manager.cryptonyan_cameras
        try:
            if self.action=='PREPARE':
                result=camera_moves.prepare(read_json(_path(s.recipe)),_path(s.bundle))
                s.status='Séquence préparée : '+result['identity'][:12]
            elif self.action=='PREVIEW':
                camera_moves.preview(_path(s.bundle),_path(s.output),_path(s.blender) if s.blender.strip() else bpy.app.binary_path)
                s.status='Aperçu créé ; ouvrir camera-preview.blend'
            else:raise ValueError('Action inconnue')
        except (ValueError,OSError,RuntimeError,KeyError,TypeError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class CRYPTONYAN_PT_cameras(bpy.types.Panel):
    bl_label='Mouvements caméra'
    bl_idname='CRYPTONYAN_PT_cameras'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='CryptoNyan'

    def draw(self,context):
        layout,s=self.layout,context.window_manager.cryptonyan_cameras
        layout.prop(s,'recipe');layout.prop(s,'bundle')
        layout.operator('cryptonyan.camera_action',text='Préparer la séquence Director').action='PREPARE'
        layout.prop(s,'output');layout.prop(s,'blender')
        layout.operator('cryptonyan.camera_action',text='Créer un aperçu Blender isolé').action='PREVIEW'
        layout.label(text='Calcul synchrone ; ouvrir la copie pour revue')
        layout.label(text=s.status)


CLASSES=(CryptoNyanCameraSettings,CRYPTONYAN_OT_camera_action,CRYPTONYAN_PT_cameras)


def register():
    if hasattr(bpy.types.WindowManager,'cryptonyan_cameras'):return
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.WindowManager.cryptonyan_cameras=PointerProperty(type=CryptoNyanCameraSettings)


def unregister():
    if not hasattr(bpy.types.WindowManager,'cryptonyan_cameras'):return
    del bpy.types.WindowManager.cryptonyan_cameras
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
