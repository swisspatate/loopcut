# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional file-based material layer tools in Blender's CryptoNyan sidebar."""
import bpy
from bpy.props import PointerProperty, StringProperty
from . import material_layers
from .animation_doctor import read_json
from .reference_ui import _path


class CryptoNyanLayerSettings(bpy.types.PropertyGroup):
    recipe: StringProperty(name="Recette de couches JSON", subtype="FILE_PATH")
    sources: StringProperty(name="Dossier des sources", subtype="DIR_PATH")
    bundle: StringProperty(name="Préparation figée", subtype="DIR_PATH")
    output: StringProperty(name="Nouveau matériau PBR", subtype="DIR_PATH")
    status: StringProperty(options={"SKIP_SAVE"})


class CRYPTONYAN_OT_layer_action(bpy.types.Operator):
    bl_idname = "cryptonyan.layer_action"
    bl_label = "Matériaux par couches"
    action: StringProperty()

    def execute(self, context):
        settings = context.window_manager.cryptonyan_layers
        try:
            if self.action == "PREPARE":
                result = material_layers.prepare(read_json(_path(settings.recipe)), _path(settings.sources), _path(settings.bundle))
                settings.status = "Sources figées : " + result["identity"][:12]
            elif self.action == "CHECK":
                result = material_layers.load_bundle(_path(settings.bundle))
                settings.status = "Préparation vérifiée : " + result["identity"][:12]
            elif self.action == "COMPOSE":
                material_layers.compose(_path(settings.bundle), _path(settings.output))
                settings.status = "Matériau PBR créé ; consulter layers.json"
            else:
                raise ValueError("Action inconnue")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class CRYPTONYAN_PT_layers(bpy.types.Panel):
    bl_label = "Matériaux par couches"
    bl_idname = "CRYPTONYAN_PT_layers"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CryptoNyan"

    def draw(self, context):
        layout, s = self.layout, context.window_manager.cryptonyan_layers
        for field in ("recipe", "sources", "bundle"):
            layout.prop(s, field)
        layout.operator("cryptonyan.layer_action", text="Figer les sources").action = "PREPARE"
        layout.operator("cryptonyan.layer_action", text="Vérifier la préparation").action = "CHECK"
        layout.prop(s, "output")
        layout.operator("cryptonyan.layer_action", text="Composer le matériau PBR").action = "COMPOSE"
        layout.label(text="Calcul local synchrone ; 1 Mpx maximum")
        layout.label(text=s.status)


CLASSES = (CryptoNyanLayerSettings, CRYPTONYAN_OT_layer_action, CRYPTONYAN_PT_layers)


def register():
    if hasattr(bpy.types.WindowManager, "cryptonyan_layers"): return
    for cls in CLASSES: bpy.utils.register_class(cls)
    bpy.types.WindowManager.cryptonyan_layers = PointerProperty(type=CryptoNyanLayerSettings)


def unregister():
    if not hasattr(bpy.types.WindowManager, "cryptonyan_layers"): return
    del bpy.types.WindowManager.cryptonyan_layers
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
