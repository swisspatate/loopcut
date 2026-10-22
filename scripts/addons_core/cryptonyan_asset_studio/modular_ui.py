# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional modular level authoring panel; output is always a new review directory."""
import bpy
from bpy.props import PointerProperty,StringProperty
from . import modular_levels
from .animation_doctor import read_json
from .reference_ui import _path


class CryptoNyanModularSettings(bpy.types.PropertyGroup):
    recipe:StringProperty(name='Recette de niveau JSON',subtype='FILE_PATH')
    catalog:StringProperty(name='Catalogue de modules JSON',subtype='FILE_PATH')
    sources:StringProperty(name='Sources GLB',subtype='DIR_PATH')
    bundle:StringProperty(name='Nouveau niveau préparé',subtype='DIR_PATH')
    output:StringProperty(name="Nouveau dossier d'aperçu",subtype='DIR_PATH')
    blender:StringProperty(name='Blender (vide = courant)',subtype='FILE_PATH')
    status:StringProperty(options={'SKIP_SAVE'})


class CRYPTONYAN_OT_modular_action(bpy.types.Operator):
    bl_idname='cryptonyan.modular_action'
    bl_label='Niveau modulaire'
    action:StringProperty()

    def execute(self,context):
        s=context.window_manager.cryptonyan_modular
        try:
            if self.action=='PREPARE':
                plan=modular_levels.prepare(read_json(_path(s.recipe)),read_json(_path(s.catalog)),_path(s.sources),_path(s.bundle))
                s.status=str(len(plan['placements']))+' modules préparés ; graphe vérifié'
            elif self.action=='CHECK':
                modular_levels.load_bundle(_path(s.bundle));s.status='Sources et plan vérifiés'
            elif self.action=='PREVIEW':
                modular_levels.preview(_path(s.bundle),_path(s.output),_path(s.blender) if s.blender.strip() else bpy.app.binary_path)
                s.status='Aperçu créé : modular-preview.blend'
            else:raise ValueError('Action inconnue')
        except (ValueError,OSError,RuntimeError,KeyError,TypeError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class CRYPTONYAN_PT_modular(bpy.types.Panel):
    bl_label='Niveaux modulaires à contraintes'
    bl_idname='CRYPTONYAN_PT_modular'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='CryptoNyan'

    def draw(self,context):
        layout,s=self.layout,context.window_manager.cryptonyan_modular
        for field in ('recipe','catalog','sources','bundle'):layout.prop(s,field)
        layout.operator('cryptonyan.modular_action',text='Composer le niveau').action='PREPARE'
        layout.operator('cryptonyan.modular_action',text='Vérifier les sources et le graphe').action='CHECK'
        layout.prop(s,'output');layout.prop(s,'blender')
        layout.operator('cryptonyan.modular_action',text='Construire un aperçu Blender isolé').action='PREVIEW'
        layout.label(text='Calcul synchrone ; contrôle Unreal requis')
        layout.label(text=s.status)


CLASSES=(CryptoNyanModularSettings,CRYPTONYAN_OT_modular_action,CRYPTONYAN_PT_modular)


def register():
    if hasattr(bpy.types.WindowManager,'cryptonyan_modular'):return
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.WindowManager.cryptonyan_modular=PointerProperty(type=CryptoNyanModularSettings)


def unregister():
    if not hasattr(bpy.types.WindowManager,'cryptonyan_modular'):return
    del bpy.types.WindowManager.cryptonyan_modular
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
