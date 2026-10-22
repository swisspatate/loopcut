# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in Blender sidebar. Network/process checks run outside Blender's UI thread."""
import json
from pathlib import Path
import queue
import threading

import bpy
from bpy.props import EnumProperty, PointerProperty, StringProperty

from .agent_connect import (
    PATH_FIELDS, SCHEMA, diagnose, export_client, load_config, save_config, validate_paths,
)

_jobs = set()


def _edited(self, context):
    self.report_json = ""


class CryptoNyanConnectionSettings(bpy.types.PropertyGroup):
    config_path: StringProperty(name="Profil de connexion", subtype="FILE_PATH", update=_edited)
    python: StringProperty(name="Python 3.11+", subtype="FILE_PATH", update=_edited)
    workspace: StringProperty(name="Dossier de travail", subtype="DIR_PATH", update=_edited)
    asset_root: StringProperty(name="Assets à traiter", subtype="DIR_PATH", update=_edited)
    blender: StringProperty(name="Blender", subtype="FILE_PATH", update=_edited)
    comfy_profiles: StringProperty(name="Catalogue ComfyUI", subtype="FILE_PATH", update=_edited)
    game_project: StringProperty(name="Projet Unreal", subtype="DIR_PATH", update=_edited)
    reference_root: StringProperty(name="Bibliothèque de références", subtype="DIR_PATH", update=_edited)
    executor: EnumProperty(name="Exécution", items=[
        ("blender", "Blender", "Traiter les missions dans un Blender séparé"),
        ("mock", "Démonstration", "Tester avec les fixtures JSON ; aucun Blender lancé"),
    ], default="blender", update=_edited)
    client: EnumProperty(name="Agent", items=[
        ("claude", "Claude Code", "Configuration JSON"),
        ("codex", "Codex", "Configuration TOML"),
    ], update=_edited)
    report_json: StringProperty(options={"SKIP_SAVE"})


def _profile(settings):
    data = {"schema": SCHEMA, "executor": settings.executor}
    for field in PATH_FIELDS:
        value = getattr(settings, field).strip()
        data[field] = str(Path(bpy.path.abspath(value)).resolve()) if value else ""
    return data


def _config_path(settings):
    if not settings.config_path.strip():
        raise ValueError("Choisir un fichier JSON pour le profil de connexion")
    return Path(bpy.path.abspath(settings.config_path)).absolute()


def _saved_profile(settings):
    path = _config_path(settings)
    if load_config(path) != _profile(settings):
        raise ValueError("Enregistrer les réglages avant de copier ou tester la connexion")
    return path


class CRYPTONYAN_OT_connection_save(bpy.types.Operator):
    bl_idname = "cryptonyan.connection_save"
    bl_label = "Enregistrer le profil"
    bl_description = "Enregistrer uniquement le profil CryptoNyan ; les réglages de l'agent restent inchangés"

    def execute(self, context):
        settings = context.window_manager.cryptonyan_connection
        try:
            config = _profile(settings)
            validate_paths(config)
            save_config(_config_path(settings), config, replace=True)
        except (ValueError, OSError, RuntimeError):
            self.report({"ERROR"}, "Vérifier les chemins, dossiers séparés et catalogue ; choisir un fichier de profil CryptoNyan")
            return {"CANCELLED"}
        settings.report_json = ""
        self.report({"INFO"}, "Profil enregistré ; configuration de l'agent disponible à copier")
        return {"FINISHED"}


class CRYPTONYAN_OT_connection_load(bpy.types.Operator):
    bl_idname = "cryptonyan.connection_load"
    bl_label = "Charger le profil"

    def execute(self, context):
        settings = context.window_manager.cryptonyan_connection
        try:
            config = load_config(_config_path(settings))
        except (ValueError, OSError, RuntimeError):
            self.report({"ERROR"}, "Profil CryptoNyan introuvable ou invalide")
            return {"CANCELLED"}
        settings.executor = config["executor"]
        for field in PATH_FIELDS:
            setattr(settings, field, config[field])
        return {"FINISHED"}


class CRYPTONYAN_OT_connection_copy(bpy.types.Operator):
    bl_idname = "cryptonyan.connection_copy"
    bl_label = "Copier la configuration de l'agent"
    bl_description = "Copier un fragment JSON/TOML à ajouter aux réglages de l'agent sélectionné"

    def execute(self, context):
        settings = context.window_manager.cryptonyan_connection
        try:
            context.window_manager.clipboard = export_client(_saved_profile(settings), settings.client)
        except (ValueError, OSError, RuntimeError):
            self.report({"ERROR"}, "Enregistrer d'abord les réglages actuels dans un profil valide")
            return {"CANCELLED"}
        self.report({"INFO"}, "Configuration copiée ; l'ajouter aux réglages MCP de l'agent et reconnecter")
        return {"FINISHED"}


def _diagnose_in_thread(results, path, client):
    # No bpy access here: only a path/client snapshot and a thread-safe result queue.
    try:
        results.put(diagnose(path, client, mcp=True, comfy=True))
    except Exception:
        results.put({"status": "blocked", "checks": [
            {"name": "diagnostic", "status": "unavailable"}]})


class CRYPTONYAN_OT_connection_check(bpy.types.Operator):
    bl_idname = "cryptonyan.connection_check"
    bl_label = "Tester MCP et ComfyUI"
    bl_description = "Tester dans un dossier temporaire, sans mission, modèle IA ni modification de scène"

    @classmethod
    def poll(cls, context):
        return context.window is not None and not _jobs

    def execute(self, context):
        settings = context.window_manager.cryptonyan_connection
        try:
            path = _saved_profile(settings)
        except (ValueError, OSError, RuntimeError):
            self.report({"ERROR"}, "Enregistrer d'abord les réglages actuels dans un profil valide")
            return {"CANCELLED"}
        self._snapshot = (str(path), _profile(settings), settings.client)
        self._results = queue.Queue(maxsize=1)
        self._manager = context.window_manager
        self._timer = self._manager.event_timer_add(0.2, window=context.window)
        _jobs.add(self)
        self._manager.modal_handler_add(self)
        settings.report_json = json.dumps({"status": "running", "checks": []})
        threading.Thread(target=_diagnose_in_thread, args=(self._results, path, settings.client), daemon=True).start()
        return {"RUNNING_MODAL"}

    def _finish(self):
        if self._timer is not None:
            self._manager.event_timer_remove(self._timer)
            self._timer = None
        _jobs.discard(self)

    def modal(self, context, event):
        if self not in _jobs:
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        try:
            report = self._results.get_nowait()
        except queue.Empty:
            return {"PASS_THROUGH"}
        settings = self._manager.cryptonyan_connection
        try:
            unchanged = self._snapshot == (str(_saved_profile(settings)), _profile(settings), settings.client)
        except (ValueError, OSError):
            unchanged = False
        # A response for previous settings must not mark edited settings as checked.
        settings.report_json = json.dumps(report) if unchanged else ""
        self._finish()
        for window in self._manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {"FINISHED"}

    def cancel(self, context):
        self._finish()


class CRYPTONYAN_PT_connections(bpy.types.Panel):
    bl_label = "Connexions des agents"
    bl_idname = "CRYPTONYAN_PT_connections"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "CryptoNyan"

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.cryptonyan_connection
        layout.prop(settings, "config_path")
        layout.operator("cryptonyan.connection_load")
        for field in ("python", "workspace", "asset_root", "executor"):
            layout.prop(settings, field)
        if settings.executor == "blender":
            layout.prop(settings, "blender")
        box = layout.box()
        box.label(text="Options ComfyUI / jeu existant")
        box.prop(settings, "comfy_profiles")
        box.prop(settings, "game_project")
        box.prop(settings, "reference_root")
        layout.operator("cryptonyan.connection_save")
        layout.prop(settings, "client")
        layout.operator("cryptonyan.connection_copy")
        layout.operator("cryptonyan.connection_check")
        layout.label(text="MCP : missions dans un Blender séparé")
        if settings.report_json:
            report = json.loads(settings.report_json)
            labels = {"ready": "Configuration valide", "checked": "Vérifications terminées",
                      "running": "Test en cours…", "blocked": "À corriger", "unavailable": "Indisponible",
                      "reachable": "Service joignable", "not_configured": "Non configuré", "not_tested": "Non testé"}
            box = layout.box()
            box.label(text=labels.get(report["status"], report["status"]))
            for check in report["checks"]:
                box.label(text=check["name"] + " : " + labels.get(check["status"], check["status"]))
            box.label(text="Connexion depuis l'agent à vérifier ensuite")


CLASSES = (CryptoNyanConnectionSettings, CRYPTONYAN_OT_connection_save, CRYPTONYAN_OT_connection_load,
           CRYPTONYAN_OT_connection_copy, CRYPTONYAN_OT_connection_check, CRYPTONYAN_PT_connections)


def register():
    if hasattr(bpy.types.WindowManager, "cryptonyan_connection"):
        return
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.cryptonyan_connection = PointerProperty(type=CryptoNyanConnectionSettings)


def unregister():
    if not hasattr(bpy.types.WindowManager, "cryptonyan_connection"):
        return
    for job in tuple(_jobs):
        job._finish()
    del bpy.types.WindowManager.cryptonyan_connection
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
