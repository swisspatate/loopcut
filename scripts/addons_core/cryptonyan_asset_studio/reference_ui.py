# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in reference sidebar; reads snapshots and prepares bundles, never edits scenes."""
import json
from pathlib import Path

import bpy
import bpy.utils.previews
from bpy.props import CollectionProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty

from . import reference_board as boards
from .animation_doctor import read_json

_previews = None


def _path(value):
    if not value.strip():
        raise ValueError("Choisir un chemin local")
    return Path(bpy.path.abspath(value)).absolute()


def _selected(settings):
    board = json.loads(settings.snapshot)
    if not 0 <= settings.index < len(board["references"]):
        raise ValueError("Sélectionner une référence")
    return board, board["references"][settings.index]


def _select(self, context):
    try:
        _, ref = _selected(self)
        self.notes = ref["notes"]
        self.target = ref["target"]["path"] if ref["target"] else ""
    except (ValueError, KeyError):
        self.notes = ""
        self.target = ""


def _folder_changed(self, context):
    self.snapshot = ""
    self.items.clear()


class CryptoNyanReferenceItem(bpy.types.PropertyGroup):
    reference_id: StringProperty()
    title: StringProperty()
    image_key: StringProperty()


class CryptoNyanReferenceSettings(bpy.types.PropertyGroup):
    folder: StringProperty(name="Dossier du tableau", subtype="DIR_PATH", update=_folder_changed)
    board_id: StringProperty(name="Identifiant", default="references")
    title: StringProperty(name="Titre du tableau", default="Références du jeu")
    project: StringProperty(name="Projet Unreal (facultatif)", subtype="DIR_PATH")
    image_file: StringProperty(name="Image PNG", subtype="FILE_PATH")
    reference_id: StringProperty(name="Identifiant image", default="reference-01")
    reference_title: StringProperty(name="Titre image", default="Nouvelle référence")
    notes: StringProperty(name="Notes", maxlen=2048)
    target: StringProperty(name="Asset relatif au projet", description="Exemple : Content/Props/Temple.uasset")
    annotation_text: StringProperty(name="Annotation", maxlen=512)
    rectangle: FloatVectorProperty(name="Zone x/y/largeur/hauteur", size=4, min=0, max=1, default=(0.1, 0.1, 0.5, 0.5))
    recipe_file: StringProperty(name="Recette Image Workshop", subtype="FILE_PATH")
    source_root: StringProperty(name="Sources GLB (facultatif)", subtype="DIR_PATH")
    output: StringProperty(name="Nouveau dossier de préparation", subtype="DIR_PATH")
    review_file: StringProperty(name="Revue HTML", subtype="FILE_PATH")
    index: IntProperty(default=0, min=0, update=_select)
    items: CollectionProperty(type=CryptoNyanReferenceItem, options={"SKIP_SAVE"})
    snapshot: StringProperty(options={"SKIP_SAVE"})
    loaded_folder: StringProperty(options={"SKIP_SAVE"})
    status: StringProperty(options={"SKIP_SAVE"})


def refresh(settings, selected=None):
    global _previews
    folder = _path(settings.folder)
    board = boards.load(folder)
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
    _previews = bpy.utils.previews.new()
    settings.items.clear()
    settings.snapshot = json.dumps(board)
    settings.loaded_folder = str(folder.resolve())
    settings.title = board["title"]
    settings.board_id = board["id"]
    for ref in board["references"]:
        item = settings.items.add()
        item.reference_id, item.title, item.image_key = ref["id"], ref["title"], ref["image"]["sha256"]
        if item.image_key not in _previews:
            _previews.load(item.image_key, str(boards.safe_path(folder, ref["image"]["file"])), "IMAGE")
    settings.index = next((i for i, ref in enumerate(board["references"]) if ref["id"] == selected),
                          min(settings.index, max(0, len(board["references"]) - 1)))
    _select(settings, bpy.context)
    settings.status = "Révision " + str(board["revision"]) + " chargée"


class CRYPTONYAN_UL_references(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if _previews is not None and item.image_key in _previews:
            layout.label(text=item.title, icon_value=_previews[item.image_key].icon_id)
        else:
            layout.label(text=item.title, icon="IMAGE_DATA")


class CRYPTONYAN_OT_reference_action(bpy.types.Operator):
    bl_idname = "cryptonyan.reference_action"
    bl_label = "Tableau de références"
    action: StringProperty()

    def execute(self, context):
        settings = context.window_manager.cryptonyan_references
        try:
            folder = _path(settings.folder)
            selected = None
            if self.action == "CREATE":
                boards.create(folder, settings.board_id, settings.title,
                              _path(settings.project) if settings.project.strip() else None)
            elif self.action == "LOAD":
                pass
            else:
                if str(folder.resolve()) != settings.loaded_folder:
                    raise ValueError("Charger le tableau avant de le modifier")
                board = json.loads(settings.snapshot)
                revision = board["revision"]
                if self.action == "ADD":
                    selected = settings.reference_id
                    boards.add(folder, revision, selected, _path(settings.image_file), settings.reference_title)
                elif self.action == "HTML":
                    boards.export_html(folder, _path(settings.review_file))
                    settings.status = "Revue HTML exportée"
                    return {"FINISHED"}
                else:
                    board, ref = _selected(settings)
                    selected = ref["id"]
                    if self.action == "NOTES":
                        boards.edit(folder, revision, selected, notes=settings.notes)
                    elif self.action == "ANNOTATE":
                        used = {mark["id"] for mark in ref["annotations"]}
                        zone = next("zone-" + str(i) for i in range(1, 18) if "zone-" + str(i) not in used)
                        regions = ref["annotations"] + [{"id": zone,
                            "text": settings.annotation_text, "rect": [round(v, 6) for v in settings.rectangle]}]
                        boards.edit(folder, revision, selected, regions=regions)
                    elif self.action == "CLEAR_ANNOTATIONS":
                        boards.edit(folder, revision, selected, regions=[])
                    elif self.action == "LINK":
                        boards.link(folder, revision, selected, settings.target)
                    elif self.action == "RECIPE":
                        boards.edit(folder, revision, selected, recipe=read_json(_path(settings.recipe_file)))
                    elif self.action == "PREPARE":
                        boards.prepare_reference(folder, revision, selected, _path(settings.output),
                            _path(settings.source_root) if settings.source_root.strip() else None)
                        settings.status = "Préparation terminée ; aucun Blender worker lancé"
                        return {"FINISHED"}
                    else:
                        raise ValueError("Action inconnue")
            refresh(settings, selected)
        except (ValueError, OSError, RuntimeError, KeyError):
            self.report({"ERROR"}, "Vérifier les chemins, le PNG, la révision, les zones et les sources ; recharger en cas de conflit")
            return {"CANCELLED"}
        return {"FINISHED"}


def _button(layout, label, action):
    layout.operator("cryptonyan.reference_action", text=label).action = action


class CRYPTONYAN_PT_references(bpy.types.Panel):
    bl_label = "Tableau de références"
    bl_idname = "CRYPTONYAN_PT_references"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CryptoNyan"

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.cryptonyan_references
        layout.prop(settings, "folder")
        _button(layout, "Charger / actualiser", "LOAD")
        if not settings.snapshot:
            for field in ("board_id", "title", "project"):
                layout.prop(settings, field)
            _button(layout, "Créer un nouveau tableau", "CREATE")
            return
        layout.label(text=settings.title)
        box = layout.box()
        for field in ("image_file", "reference_id", "reference_title"):
            box.prop(settings, field)
        _button(box, "Ajouter la référence PNG", "ADD")
        layout.template_list("CRYPTONYAN_UL_references", "", settings, "items", settings, "index", rows=3)
        if settings.items and settings.index < len(settings.items):
            item = settings.items[settings.index]
            if _previews is not None and item.image_key in _previews:
                layout.template_icon(icon_value=_previews[item.image_key].icon_id, scale=8)
            layout.prop(settings, "notes")
            _button(layout, "Enregistrer les notes", "NOTES")
            box = layout.box()
            box.label(text="Zones : origine en haut à gauche, valeurs 0–1")
            box.prop(settings, "annotation_text")
            box.prop(settings, "rectangle")
            _button(box, "Ajouter la zone annotée", "ANNOTATE")
            _, ref = _selected(settings)
            for index, mark in enumerate(ref["annotations"], 1):
                box.label(text=str(index) + ". " + mark["text"][:60])
            if ref["annotations"]:
                _button(box, "Effacer les annotations", "CLEAR_ANNOTATIONS")
            layout.prop(settings, "target")
            _button(layout, "Lier / actualiser l'empreinte de l'asset", "LINK")
            box = layout.box()
            box.prop(settings, "recipe_file")
            _button(box, "Attacher la recette JSON", "RECIPE")
            box.prop(settings, "source_root")
            box.prop(settings, "output")
            _button(box, "Préparer pour Image Workshop", "PREPARE")
        layout.prop(settings, "review_file")
        _button(layout, "Exporter les images et zones en HTML", "HTML")
        if settings.status:
            layout.label(text=settings.status)


CLASSES = (CryptoNyanReferenceItem, CryptoNyanReferenceSettings, CRYPTONYAN_UL_references,
           CRYPTONYAN_OT_reference_action, CRYPTONYAN_PT_references)


def register():
    if hasattr(bpy.types.WindowManager, "cryptonyan_references"):
        return
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.cryptonyan_references = PointerProperty(type=CryptoNyanReferenceSettings)


def unregister():
    global _previews
    if not hasattr(bpy.types.WindowManager, "cryptonyan_references"):
        return
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
    del bpy.types.WindowManager.cryptonyan_references
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
