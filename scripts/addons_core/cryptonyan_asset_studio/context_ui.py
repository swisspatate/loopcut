# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit selection exports and offline mask authoring from reference snapshots."""
import json
from pathlib import Path
import webbrowser

import bpy
from bpy.props import PointerProperty, StringProperty
from . import scene_selection, mask_paint, reference_board
from .animation_doctor import read_json
from .reference_ui import _path, _selected


def _reset_source(self, context):
    self.protected_root = ""


class CryptoNyanContextSettings(bpy.types.PropertyGroup):
    library: StringProperty(name="Bibliothèque (vide = profil)", subtype="DIR_PATH")
    snapshot_id: StringProperty(name="Nouvel identifiant", default="selection-01")
    status: StringProperty(options={"SKIP_SAVE"})


class CryptoNyanMaskSettings(bpy.types.PropertyGroup):
    reference: StringProperty(name="Référence PNG", subtype="FILE_PATH", update=_reset_source)
    editor: StringProperty(name="Nouvel éditeur HTML", subtype="FILE_PATH")
    strokes: StringProperty(name="Tracé JSON téléchargé", subtype="FILE_PATH")
    output: StringProperty(name="Nouveau dossier du masque", subtype="DIR_PATH")
    protected_root: StringProperty(options={"SKIP_SAVE"})
    status: StringProperty(options={"SKIP_SAVE"})


def _mask_source(context, image, protected_root):
    settings = context.window_manager.cryptonyan_masks
    settings.reference = str(image)
    settings.protected_root = str(protected_root)
    settings.status = "Référence sélectionnée ; créer l'éditeur HTML"


class CRYPTONYAN_OT_context_export(bpy.types.Operator):
    bl_idname = "cryptonyan.context_export"
    bl_label = "Exporter la sélection pour l'agent"
    action: StringProperty()

    def execute(self, context):
        settings = context.window_manager.cryptonyan_context
        try:
            connection = context.window_manager.cryptonyan_connection
            library = _path(settings.library if settings.library.strip() else connection.reference_root)
            if connection.game_project.strip():
                reference_board._separate(library, _path(connection.game_project))
            if self.action not in ("METADATA", "VIEWPORT"):
                raise ValueError("Action inconnue")
            value = scene_selection.capture(library, settings.snapshot_id, viewport=self.action == "VIEWPORT", context=context)
            if value["image"]:
                folder = library / "scene-contexts" / settings.snapshot_id
                _mask_source(context, folder / "view.png", folder)
            settings.status = "Instantané créé : " + value["identity"][:12]
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class CRYPTONYAN_OT_mask_action(bpy.types.Operator):
    bl_idname = "cryptonyan.mask_action"
    bl_label = "Peindre un masque sur une référence"
    action: StringProperty()

    def execute(self, context):
        settings = context.window_manager.cryptonyan_masks
        try:
            if self.action == "REFERENCE":
                ui = context.window_manager.cryptonyan_references
                board, ref = _selected(ui)
                folder = _path(ui.folder).resolve()
                if str(folder) != ui.loaded_folder or reference_board.load(folder) != board:
                    raise ValueError("Recharger le tableau de références")
                _mask_source(context, reference_board.safe_path(folder, ref["image"]["file"]), folder)
                return {"FINISHED"}
            if self.action == "OPEN":
                path = _path(settings.editor)
                if not path.is_file() or path.suffix.lower() != ".html":
                    raise ValueError("Créer l'éditeur HTML avant de l'ouvrir")
                webbrowser.open(path.as_uri())
                return {"FINISHED"}
            output = _path(settings.editor if self.action == "EDITOR" else settings.output)
            if settings.protected_root:
                reference_board._separate(_path(settings.protected_root), output)
            if self.action == "EDITOR":
                mask_paint.editor(_path(settings.reference), output)
                settings.status = "Éditeur créé ; ouvrir puis télécharger le tracé JSON"
            elif self.action == "RENDER":
                result = mask_paint.render(read_json(_path(settings.strokes)), _path(settings.reference), output)
                settings.status = "Masque PBR créé : " + result["mask"]["sha256"][:12]
            else:
                raise ValueError("Action inconnue")
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class CRYPTONYAN_PT_context(bpy.types.Panel):
    bl_label = "Contexte de sélection pour l'agent"
    bl_idname = "CRYPTONYAN_PT_context"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CryptoNyan"

    def draw(self, context):
        layout, s = self.layout, context.window_manager.cryptonyan_context
        layout.prop(s, "library"); layout.prop(s, "snapshot_id")
        layout.operator("cryptonyan.context_export", text="Exporter les informations").action = "METADATA"
        layout.operator("cryptonyan.context_export", text="Exporter avec le viewport").action = "VIEWPORT"
        layout.label(text=s.status)


class CRYPTONYAN_PT_masks(bpy.types.Panel):
    bl_label = "Masques interactifs sur image"
    bl_idname = "CRYPTONYAN_PT_masks"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CryptoNyan"

    def draw(self, context):
        layout, s = self.layout, context.window_manager.cryptonyan_masks
        layout.operator("cryptonyan.mask_action", text="Utiliser la référence du tableau").action = "REFERENCE"
        layout.prop(s, "reference"); layout.prop(s, "editor")
        layout.operator("cryptonyan.mask_action", text="Créer l'éditeur local").action = "EDITOR"
        layout.operator("cryptonyan.mask_action", text="Ouvrir dans le navigateur").action = "OPEN"
        layout.prop(s, "strokes"); layout.prop(s, "output")
        layout.operator("cryptonyan.mask_action", text="Importer le tracé et produire le PNG").action = "RENDER"
        layout.label(text=s.status)


CLASSES = (CryptoNyanContextSettings, CryptoNyanMaskSettings, CRYPTONYAN_OT_context_export,
           CRYPTONYAN_OT_mask_action, CRYPTONYAN_PT_context, CRYPTONYAN_PT_masks)


def register():
    if hasattr(bpy.types.WindowManager, "cryptonyan_context"): return
    for cls in CLASSES: bpy.utils.register_class(cls)
    bpy.types.WindowManager.cryptonyan_context = PointerProperty(type=CryptoNyanContextSettings)
    bpy.types.WindowManager.cryptonyan_masks = PointerProperty(type=CryptoNyanMaskSettings)


def unregister():
    if not hasattr(bpy.types.WindowManager, "cryptonyan_context"): return
    del bpy.types.WindowManager.cryptonyan_context
    del bpy.types.WindowManager.cryptonyan_masks
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
