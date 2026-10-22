# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in sidebar for existing-rig try-on; never evaluates the active scene."""
import bpy
from bpy.props import PointerProperty, StringProperty
from . import wardrobe_review
from .animation_doctor import read_json
from .executors import BudgetExpired, WorkerFailure
from .reference_ui import _path


class CryptoNyanWardrobeSettings(bpy.types.PropertyGroup):
    source: StringProperty(name='Copie source .blend', subtype='FILE_PATH')
    specification: StringProperty(name='Actions et vêtements JSON', subtype='FILE_PATH')
    output: StringProperty(name='Nouveau dossier de revue', subtype='DIR_PATH')
    blender: StringProperty(name='Blender (vide = courant)', subtype='FILE_PATH')
    status: StringProperty(options={'SKIP_SAVE'})


class CRYPTONYAN_OT_wardrobe_review(bpy.types.Operator):
    bl_idname = 'cryptonyan.wardrobe_review'
    bl_label = 'Examiner les vêtements animés'

    def execute(self, context):
        s = context.window_manager.cryptonyan_wardrobe
        try:
            receipt = wardrobe_review.run(_path(s.source), read_json(_path(s.specification)), _path(s.output),
                _path(s.blender) if s.blender.strip() else bpy.app.binary_path)
            s.status = f'{receipt["flagged_samples"]} poses/vêtements signalés ; ouvrir review.html'
        except (ValueError, OSError, RuntimeError, KeyError, TypeError, BudgetExpired, WorkerFailure) as exc:
            self.report({'ERROR'}, str(exc) or type(exc).__name__); return {'CANCELLED'}
        return {'FINISHED'}


class CRYPTONYAN_PT_wardrobe(bpy.types.Panel):
    bl_label = 'Essayage des vêtements animés'
    bl_idname = 'CRYPTONYAN_PT_wardrobe'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'CryptoNyan'

    def draw(self, context):
        layout, s = self.layout, context.window_manager.cryptonyan_wardrobe
        for field in ('source', 'specification', 'output', 'blender'):
            layout.prop(s, field)
        layout.operator('cryptonyan.wardrobe_review')
        layout.label(text='Calcul synchrone dans un Blender isolé')
        layout.label(text=s.status)


CLASSES = (CryptoNyanWardrobeSettings, CRYPTONYAN_OT_wardrobe_review, CRYPTONYAN_PT_wardrobe)


def register():
    if hasattr(bpy.types.WindowManager, 'cryptonyan_wardrobe'):
        return
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.cryptonyan_wardrobe = PointerProperty(type=CryptoNyanWardrobeSettings)


def unregister():
    if not hasattr(bpy.types.WindowManager, 'cryptonyan_wardrobe'):
        return
    del bpy.types.WindowManager.cryptonyan_wardrobe
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
