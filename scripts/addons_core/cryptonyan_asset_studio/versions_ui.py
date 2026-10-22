# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional Blender sidebar for candidate archives; never opens or replaces a scene."""
import json
import bpy
from bpy.props import PointerProperty, StringProperty
from . import visual_versions as versions
from .reference_ui import _path, _selected


class CryptoNyanVersionSettings(bpy.types.PropertyGroup):
    folder: StringProperty(name="Dossier historique", subtype="DIR_PATH")
    asset_id: StringProperty(name="Identifiant asset", default="temple")
    title: StringProperty(name="Titre", default="Variantes du temple")
    project: StringProperty(name="Projet Unreal (facultatif)", subtype="DIR_PATH")
    attempt: StringProperty(name="Candidat Image Workshop", subtype="DIR_PATH")
    version_id: StringProperty(name="Version", default="v01")
    label: StringProperty(name="Description", default="Premier candidat")
    other: StringProperty(name="Comparer avec", default="v02")
    output: StringProperty(name="Nouveau dossier restauré", subtype="DIR_PATH")
    review: StringProperty(name="Comparaison HTML", subtype="FILE_PATH")
    snapshot: StringProperty(options={"SKIP_SAVE"})
    loaded_folder: StringProperty(options={"SKIP_SAVE"})
    status: StringProperty(options={"SKIP_SAVE"})


class CRYPTONYAN_OT_version_action(bpy.types.Operator):
    bl_idname = "cryptonyan.version_action"
    bl_label = "Versions visuelles"
    action: StringProperty()

    def execute(self, context):
        s = context.window_manager.cryptonyan_versions
        try:
            folder = _path(s.folder).resolve()
            if self.action == "CREATE":
                versions.create(folder, s.asset_id, s.title, _path(s.project) if s.project.strip() else None)
            elif self.action == "LOAD":
                pass
            else:
                if str(folder) != s.loaded_folder:
                    raise ValueError("Charger l'historique")
                history = json.loads(s.snapshot)
                if self.action in ("ARCHIVE", "ARCHIVE_BOARD"):
                    board_folder, reference = None, None
                    if self.action == "ARCHIVE_BOARD":
                        board = context.window_manager.cryptonyan_references
                        loaded, ref = _selected(board)
                        board_folder = _path(board.folder).resolve()
                        if str(board_folder) != board.loaded_folder:
                            raise ValueError("Recharger le tableau")
                        from .reference_board import load
                        if load(board_folder) != loaded:
                            raise ValueError("Le tableau a changé ; recharger")
                        reference = ref["id"]
                    versions.archive(folder, history["revision"], s.version_id, _path(s.attempt), s.label, board_folder, reference)
                elif self.action == "SELECT":
                    versions.select(folder, history["revision"], s.version_id)
                elif self.action == "RESTORE":
                    versions.restore(folder, s.version_id, _path(s.output))
                    s.status = "Copie restaurée ; scène et jeu inchangés"
                    return {"FINISHED"}
                elif self.action == "COMPARE":
                    versions.compare(folder, s.version_id, s.other, _path(s.review))
                    s.status = "Comparaison HTML créée"
                    return {"FINISHED"}
                else:
                    raise ValueError("Action inconnue")
            value = versions.load(folder)
            s.snapshot, s.loaded_folder = json.dumps(value), str(folder)
            s.status = "Révision " + str(value["revision"]) + " ; sélection : " + str(value["selected"] or "aucune")
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class CRYPTONYAN_PT_versions(bpy.types.Panel):
    bl_label = "Versions visuelles"
    bl_idname = "CRYPTONYAN_PT_versions"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CryptoNyan"

    def draw(self, context):
        layout, s = self.layout, context.window_manager.cryptonyan_versions
        layout.prop(s, "folder")
        for field in ("asset_id", "title", "project"):
            layout.prop(s, field)
        row = layout.row()
        for action, label in (("CREATE", "Créer"), ("LOAD", "Charger")):
            row.operator("cryptonyan.version_action", text=label).action = action
        if s.snapshot:
            for item in json.loads(s.snapshot)["versions"]:
                layout.label(text=item["id"] + " : " + item["label"], icon="FILE_BLEND")
        for field in ("attempt", "version_id", "label"):
            layout.prop(s, field)
        layout.operator("cryptonyan.version_action", text="Archiver le candidat").action = "ARCHIVE"
        layout.operator("cryptonyan.version_action", text="Archiver avec la référence sélectionnée").action = "ARCHIVE_BOARD"
        layout.operator("cryptonyan.version_action", text="Retenir cette version").action = "SELECT"
        layout.prop(s, "other"); layout.prop(s, "review")
        layout.operator("cryptonyan.version_action", text="Comparer les rendus (HTML)").action = "COMPARE"
        layout.prop(s, "output")
        layout.operator("cryptonyan.version_action", text="Restaurer une copie").action = "RESTORE"
        layout.label(text=s.status)


CLASSES = (CryptoNyanVersionSettings, CRYPTONYAN_OT_version_action, CRYPTONYAN_PT_versions)


def register():
    if hasattr(bpy.types.WindowManager, "cryptonyan_versions"):
        return
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.cryptonyan_versions = PointerProperty(type=CryptoNyanVersionSettings)


def unregister():
    if not hasattr(bpy.types.WindowManager, "cryptonyan_versions"):
        return
    del bpy.types.WindowManager.cryptonyan_versions
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
