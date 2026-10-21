# SPDX-License-Identifier: GPL-3.0-or-later
"""Recipe tests and strict editor protocol doubles, NOT an Unreal runtime test."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.creative_director import recipe, operations, make_plan, load_plan, import_contacts, write_new
from cryptonyan_asset_studio.unreal_director import execute, CHANNELS, TRACK
from cryptonyan_asset_studio.storage import digest, write_json

ANIM, MESH, FX, WALL = "/Game/Run.Run", "/Game/Cat.Cat", "/Game/Dust.Dust", "/Game/Wall.Wall"
DEST = "/Game/CryptoNyan/DirectedReviews/Test"
MAP = "/Game/CryptoNyan/ReviewMaps/DirectorTest"


def effects():
    return {"kind": "effects", "destination": DEST, "animation": ANIM, "preview_mesh": MESH, "duration_s": 1,
            "events": [{"id": "LeftContact", "kind": "contact", "time_s": .25, "socket": "PawL", "niagara": FX,
                        "attached": False, "offset_m": [0, 0, .02], "scale": [1, 1, 1], "reviewed": True}]}


def cinematic():
    return {"kind": "cinematic", "destination": DEST, "fps": 30,
            "shots": [{"id": "Reveal", "frames": 60, "keys": [
                {"frame": 0, "position_m": [-10, -2, 3], "rotation_rpy_deg": [0, -10, 179]},
                {"frame": 59, "position_m": [-5, 2, 2], "rotation_rpy_deg": [0, 0, -179]}]},
                {"id": "Detail", "frames": 30, "keys": [
                {"frame": 0, "position_m": [1, 1, 1], "rotation_rpy_deg": [0, 0, 0]},
                {"frame": 29, "position_m": [1, 2, 1], "rotation_rpy_deg": [0, 0, 20]}]}]}


def architecture():
    return {"kind": "architecture", "destination": DEST, "target_level": MAP,
            "anchor_m": [10, 20, 1], "yaw_deg": 90, "modules": {"wall": WALL},
            "rows": [{"id": "Facade", "module": "wall", "count": 3, "origin_m": [0, 0, 0],
                      "step_m": [2, 0, 0], "yaw_deg": 10, "scale": [1, 1, 1]}]}


class Obj:
    def __init__(self, path="", kind="Object", **properties):
        self.path, self.kind, self.properties = path, kind, properties

    def get_path_name(self):
        return self.path

    def get_class(self):
        return NS(get_name=lambda: self.kind)

    def get_editor_property(self, name):
        return self.properties[name]

    def set_editor_property(self, name, value):
        self.properties[name] = value


class Channel(Obj):
    def __init__(self, name):
        super().__init__(channel_name=name)
        self.keys = []

    def add_key(self, frame, value, *, time_unit, interpolation):
        assert time_unit == "display" and interpolation == "linear"
        self.keys.append((frame.value, value))
        return NS(get_value=lambda: value, get_time=lambda **kw: NS(frame_number=frame, sub_frame=0))


class Section:
    def __init__(self):
        self.channels = [Channel(n) for n in reversed(CHANNELS)]
        self.binding = None

    def set_range(self, start, end):
        self.start, self.end = start, end

    def get_all_channels(self):
        return self.channels

    def set_camera_binding_id(self, value):
        self.binding = value

    def get_camera_binding_id(self):
        return self.binding


class Track:
    def __init__(self, kind):
        self.kind, self.sections = kind, []

    def add_section(self):
        result = Section()
        self.sections.append(result)
        return result


class Binding:
    def __init__(self, identity):
        self.identity, self.tracks = identity, []

    def is_valid(self):
        return True

    def set_display_name(self, name):
        self.name = name

    def add_track(self, kind):
        track = Track(kind)
        self.tracks.append(track)
        return track


class Sequence(Obj):
    def __init__(self, path):
        super().__init__(path, "LevelSequence")
        self.tracks, self.bindings = [], []

    def set_display_rate(self, value):
        self.rate = value

    def set_playback_start(self, value):
        self.start = value

    def set_playback_end(self, value):
        self.end = value

    def add_track(self, kind):
        result = Track(kind)
        self.tracks.append(result)
        return result


class Actor(Obj):
    def __init__(self, path, location, rotation):
        super().__init__(path, "StaticMeshActor")
        self.location, self.rotation, self.component = location, rotation, Obj()
        self.component.set_static_mesh = self.set_mesh

    def set_mesh(self, value):
        self.component.properties["static_mesh"] = value
        return True

    def set_actor_label(self, label):
        self.label = label

    def get_component_by_class(self, kind):
        return self.component

    def set_actor_scale3d(self, value):
        self.scale = value

    def get_actor_location(self):
        return self.location

    def get_actor_scale3d(self):
        return self.scale

    def get_actor_rotation(self):
        return self.rotation


class Editor:
    """Only the explicitly exercised API surface exists; unknown calls fail."""
    AnimNotify_PlayNiagaraEffect = object
    LevelSequence = "LevelSequence"
    LevelSequenceFactoryNew = object
    LevelSequenceEditorSubsystem = "sequencer"
    EditorActorSubsystem = "actors"
    UnrealEditorSubsystem = "editor"
    CineCameraActor = "camera"
    StaticMeshActor = "static_mesh"
    StaticMeshComponent = "mesh_component"
    MovieSceneCameraCutTrack = "camera_cuts"
    MovieScene3DTransformTrack = "transform"
    MovieSceneTimeUnit = NS(DISPLAY_RATE="display")
    MovieSceneKeyInterpolation = NS(LINEAR="linear")
    Name = str
    FrameRate = NS
    Rotator = NS
    FrameNumber = staticmethod(lambda value: NS(value=value))
    Vector = staticmethod(lambda x, y, z: NS(x=x, y=y, z=z))

    def __init__(self, root):
        self.root = root
        self.objects, self.dirs, self.saved, self.actors, self.removed = {}, set(), [], [], []
        self.version, self.dirty, self.sockets = "5.8.3-test", [], {"PawL"}
        self.world = Obj(MAP+".DirectorTest", "World")
        self.fail_spawn_at, self.fail_save, self.on_create, self.bad_channels = None, False, None, False
        self.SystemLibrary = NS(get_engine_version=lambda: self.version)
        self.Paths = NS(project_dir=lambda: str(self.root))
        self.EditorLoadingAndSavingUtils = NS(get_dirty_content_packages=lambda: [Obj(p) for p in self.dirty])
        self.EditorAssetLibrary = NS(does_directory_exist=lambda p: p in self.dirs,
            list_assets=lambda p, **kw: [n for n in self.objects if n.startswith(p+"/")],
            make_directory=self.reserve, save_loaded_asset=self.save)
        self.AssetToolsHelpers = NS(get_asset_tools=lambda: NS(duplicate_asset=self.duplicate, create_asset=self.create))
        self.AnimationLibrary = NS(get_sequence_length=lambda a: a.properties["duration"],
            get_animation_notify_track_names=lambda a: a.properties["tracks"],
            get_animation_notify_events=lambda a: a.properties["notifies"],
            add_animation_notify_track=lambda a, n: a.properties["tracks"].append(n),
            add_animation_notify_event=self.notify,
            get_animation_notify_events_for_track=lambda a, n: [e for e in a.properties["notifies"] if e.track == n],
            get_anim_notify_event_trigger_time=lambda e: e.time)
        self.MovieSceneSequenceExtensions = NS(get_binding_id=lambda seq, b: b.identity)

    def add(self, path, kind, **properties):
        obj = Obj(path, kind, **properties)
        self.objects[path] = obj
        file = self.root / ("Content/"+path.split(".")[0][6:]+".uasset")
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(("Opaque test package: "+path).encode())
        return obj

    def load_asset(self, path):
        return self.objects.get(path)

    def reserve(self, path):
        self.dirs.add(path)
        return True

    def save(self, obj, **kw):
        if self.fail_save:
            return False
        self.saved.append(obj.path)
        return True

    def duplicate(self, name, directory, original):
        obj = copy.deepcopy(original)
        obj.path = directory+"/"+name+"."+name
        self.objects[obj.path] = obj
        if self.on_create:
            self.on_create(obj)
        return obj

    def create(self, name, directory, kind, factory):
        assert kind == "LevelSequence"
        seq = Sequence(directory+"/"+name+"."+name)
        self.objects[seq.path] = seq
        if self.on_create:
            self.on_create(seq)
        return seq

    def notify(self, anim, track, time, kind):
        obj = Obj()
        anim.properties["notifies"].append(NS(track=track, time=time, notify=obj))
        return obj

    def SkeletalMeshComponent(self):
        return NS(set_skeletal_mesh_asset=lambda m: None, does_socket_exist=lambda n: n in self.sockets)

    def get_editor_subsystem(self, kind):
        if kind == "sequencer":
            return NS(add_spawnable_from_class=self.camera)
        if kind == "editor":
            return NS(get_editor_world=lambda: self.world)
        assert kind == "actors"
        return NS(get_all_level_actors=lambda: [Obj("WorldSettings", "WorldSettings"), *self.actors],
                  spawn_actor_from_class=self.spawn, destroy_actor=self.destroy)

    def camera(self, seq, kind):
        assert kind == "camera"
        binding = Binding(len(seq.bindings)+1)
        seq.bindings.append(binding)
        if self.bad_channels:
            binding.add_track = lambda kind: NS(add_section=lambda: NS(set_range=lambda *a: None, get_all_channels=lambda: []))
        return binding

    def spawn(self, kind, location, rotation):
        if len(self.actors) == self.fail_spawn_at:
            return None
        actor = Actor("Actor_"+str(len(self.actors)), location, rotation)
        self.actors.append(actor)
        return actor

    def destroy(self, actor):
        self.actors.remove(actor)
        self.removed.append(actor.path)
        return True


class DirectorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.project = self.folder / "game"
        self.project.mkdir()
        write_json(self.project / "Test.uproject", {"FileVersion": 3, "EngineAssociation": "5.8"})
        self.u = Editor(self.project)
        skeleton = Obj("/Game/Skeleton.Skeleton", "Skeleton")
        self.u.add(ANIM, "AnimSequence", skeleton=skeleton, duration=1, tracks=["Original"],
                   notifies=[NS(track="Original", time=.5, notify=Obj())])
        self.u.add(MESH, "SkeletalMesh", skeleton=skeleton)
        self.u.add(FX, "NiagaraSystem")
        self.u.add(WALL, "StaticMesh")

    def plan(self, spec):
        plan = make_plan(spec, self.project)
        path = self.folder / "plan.json"
        write_json(path, plan)
        return path

    def run_editor(self, spec, **kw):
        return execute(self.plan(spec), self.folder / "receipt.json", apply=True, unreal_module=self.u, **kw)

    def test_recipe_roundtrip_and_plan_determinism_no_input_mutation(self):
        for spec in (effects(), cinematic(), architecture()):
            before = copy.deepcopy(spec)
            a = make_plan(spec, self.project)
            self.assertEqual(a, make_plan(json.loads(json.dumps(spec)), self.project))
            self.assertEqual(spec, before)
            self.assertFalse(a["engine_validated"])

    def test_effect_bounds_reviews_duplicates_and_asset_roles(self):
        for change in ({"time_s": 1}, {"time_s": float("nan")}, {"reviewed": False}, {"reviewed": 1},
                       {"scale": [0, 1, 1]}, {"attached": 1}, {"niagara": ANIM}, {"socket": ""}):
            spec = effects()
            spec["events"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                recipe(spec)
        spec = effects()
        spec["events"].append({**spec["events"][0], "id": "Second"})
        with self.assertRaises(ValueError):
            recipe(spec)

    def test_cinematic_contiguous_ranges_cm_and_short_rotation_path(self):
        result = operations(cinematic())
        self.assertEqual([(s["start"], s["end"]) for s in result], [(0, 60), (60, 90)])
        self.assertEqual(result[0]["keys"][0]["position_cm"], [-1000, -200, 300])
        self.assertEqual(result[0]["keys"][-1]["rotation_rpy_deg"], [0, 0, 181])
        self.assertEqual(result[1]["keys"][-1]["frame"], 89)

    def test_cinematic_frame_order_endpoints_and_budgets(self):
        for mutate in (lambda s: s.update(fps=True), lambda s: s["shots"][0]["keys"][0].update(frame=1),
                       lambda s: s["shots"][0]["keys"][-1].update(frame=60),
                       lambda s: s["shots"][0].update(frames=100000),
                       lambda s: s.update(shots=s["shots"]*9)):
            spec = cinematic()
            mutate(spec)
            with self.assertRaises(ValueError):
                recipe(spec)

    def test_architecture_reuses_mesh_rotates_anchor_and_scales(self):
        result = operations(architecture())
        self.assertEqual(len(result), 3)
        self.assertEqual({r["mesh"] for r in result}, {WALL})
        for i, row in enumerate(result):
            self.assertAlmostEqual(row["position_cm"][0], 1000)
            self.assertAlmostEqual(row["position_cm"][1], 2000+i*200)
            self.assertEqual(row["yaw_deg"], 100)

    def test_architecture_rejects_coincidence_and_oversized_layout(self):
        spec = architecture()
        spec["rows"][0]["step_m"] = [0, 0, 0]
        with self.assertRaises(ValueError):
            operations(spec)
        spec["rows"][0]["count"] = 257
        with self.assertRaises(ValueError):
            recipe(spec)

    def test_destination_and_unknown_fields_rejected(self):
        for spec in (effects(), cinematic(), architecture()):
            with self.assertRaises(ValueError):
                recipe({**spec, "destination": "/Game/Existing"})
            with self.assertRaises(ValueError):
                recipe({**spec, "execute": "script"})

    def test_pins_include_package_sidecars_and_source_change_blocks_apply(self):
        extra = self.project / "Content/Run.uexp"
        extra.write_bytes(b"sidecar")
        path = self.plan(effects())
        self.assertEqual(len(load_plan(path)["sources"][ANIM]), 2)
        extra.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            execute(path, self.folder / "receipt.json", apply=True, unreal_module=self.u)
        self.assertFalse(self.u.dirs)
        self.assertFalse((self.folder / "receipt.json").exists())

    def test_lfs_source_rejected(self):
        (self.project / "Content/Run.uasset").write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\n")
        with self.assertRaises(ValueError):
            self.plan(effects())

    def test_modified_operations_and_descriptor_rejected(self):
        path = self.plan(architecture())
        data = json.loads(path.read_text())
        data["operations"][0]["mesh"] = ANIM
        write_json(path, data)
        with self.assertRaises(ValueError):
            load_plan(path)
        path = self.plan(cinematic())
        write_json(self.project / "Test.uproject", {"FileVersion": 3, "EngineAssociation": "5.8.3"})
        with self.assertRaises(ValueError):
            load_plan(path)

    def test_dry_run_requires_no_unreal_and_does_not_write_game(self):
        path = self.plan(effects())
        before = {p.name: digest(p) for p in self.project.rglob("*.uasset")}
        result = execute(path, self.folder / "dry.json")
        self.assertEqual(result["status"], "planned")
        self.assertEqual(before, {p.name: digest(p) for p in self.project.rglob("*.uasset")})
        self.assertFalse(self.u.dirs)

    def test_reports_and_plans_cannot_overwrite_or_write_inside_project(self):
        path = self.plan(effects())
        with self.assertRaises(ValueError):
            execute(path, self.project / "receipt.json")
        with self.assertRaises(ValueError):
            write_new(self.project / "new.json", {}, self.project)
        execute(path, self.folder / "dry.json")
        with self.assertRaises(FileExistsError):
            execute(path, self.folder / "dry.json")

    def test_effect_copy_notify_properties_timing_and_original_preserved(self):
        source = self.u.objects[ANIM]
        before = digest(self.project / "Content/Run.uasset")
        result = self.run_editor(effects())
        self.assertEqual(result["status"], "created_review_required", result)
        self.assertEqual(self.u.saved, [DEST+"/AN_Directed.AN_Directed"])
        candidate = self.u.objects[self.u.saved[0]]
        self.assertEqual(len(candidate.properties["notifies"]), 2)
        event = candidate.properties["notifies"][-1]
        self.assertEqual((event.track, event.time), (TRACK, .25))
        self.assertEqual(event.notify.properties["location_offset"].z, 2)
        self.assertFalse(event.notify.properties["should_fire_in_editor"])
        self.assertEqual(source.properties["tracks"], ["Original"])
        self.assertEqual(len(source.properties["notifies"]), 1)
        self.assertEqual(digest(self.project / "Content/Run.uasset"), before)

    def test_existing_effect_track_prevents_duplicate_layer(self):
        self.u.objects[ANIM].properties["tracks"].append(TRACK)
        result = self.run_editor(effects())
        self.assertEqual(result["error"], "source_already_has_directed_effects")
        self.assertFalse(self.u.dirs)

    def test_missing_socket_blocks_before_duplicate(self):
        self.u.sockets.clear()
        result = self.run_editor(effects())
        self.assertEqual(result["error"], "missing_effect_bone_or_socket")
        self.assertFalse(self.u.dirs)

    def test_skeleton_mismatch_blocks_before_duplicate(self):
        self.u.objects[MESH].properties["skeleton"] = Obj("/Game/Different.Different")
        result = self.run_editor(effects())
        self.assertEqual(result["error"], "animation_mesh_skeleton_mismatch")
        self.assertFalse(self.u.dirs)

    def test_clip_duration_mismatch_blocks_before_duplicate(self):
        self.u.objects[ANIM].properties["duration"] = 2
        result = self.run_editor(effects())
        self.assertEqual(result["error"], "animation_duration_mismatch")
        self.assertFalse(self.u.dirs)

    def test_dirty_content_or_wrong_engine_blocks_before_mutation(self):
        self.u.dirty = ["/Game/Run"]
        result = self.run_editor(effects())
        self.assertEqual(result["error"], "save_content_changes_before_director_run")
        self.assertFalse(self.u.dirs)
        (self.folder / "receipt.json").unlink()
        self.u.dirty, self.u.version = [], "5.7.0"
        result = self.run_editor(cinematic())
        self.assertEqual(result["status"], "failed")
        self.assertFalse(self.u.dirs)

    def test_wrong_source_class_and_redirector_rejected(self):
        self.u.objects[FX].kind = "Texture2D"
        result = self.run_editor(effects())
        self.assertEqual(result["error"], "missing_source_wrong_class_or_redirector")
        self.assertFalse(self.u.dirs)

    def test_existing_destination_is_not_reused(self):
        self.u.dirs.add(DEST)
        result = self.run_editor(cinematic())
        self.assertEqual(result["error"], "director_destination_exists")
        self.assertFalse(self.u.saved)

    def test_source_changed_during_creation_keeps_failed_owned_copy_unsaved(self):
        self.u.on_create = lambda obj: (self.project / "Content/Run.uasset").write_bytes(b"changed")
        result = self.run_editor(effects())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["owned_assets"]), 1)
        self.assertFalse(self.u.saved)

    def test_save_failure_is_explicit_and_partial_copy_is_retained(self):
        self.u.fail_save = True
        result = self.run_editor(effects())
        self.assertEqual(result["error"], "director_save_failed")
        self.assertEqual(len(result["owned_assets"]), 1)
        self.assertEqual(result["saved_assets"], [])

    def test_duplicate_returning_original_is_never_owned_or_mutated(self):
        self.u.duplicate = lambda *a: self.u.objects[ANIM]
        result = self.run_editor(effects())
        self.assertEqual(result["error"], "candidate_creation_mismatch")
        self.assertEqual(result["owned_assets"], [])
        self.assertEqual(self.u.objects[ANIM].properties["tracks"], ["Original"])

    def test_failed_rollback_reports_remaining_actor(self):
        self.u.fail_spawn_at = 1
        self.u.destroy = lambda actor: False
        result = self.run_editor(architecture())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["remaining_actors"], ["Actor_0"])
        self.assertEqual(len(self.u.actors), 1)

    def test_cinematic_actual_adapter_wires_cuts_keys_and_named_channels(self):
        result = self.run_editor(cinematic())
        self.assertEqual(result["status"], "created_review_required", result)
        seq = self.u.objects[result["saved_assets"][0]]
        self.assertEqual((seq.start, seq.end, seq.rate.numerator), (0, 90, 30))
        cuts = seq.tracks[0].sections
        self.assertEqual([(c.start, c.end, c.binding) for c in cuts], [(0, 60, 1), (60, 90, 2)])
        channels = {c.properties["channel_name"]: c for c in seq.bindings[0].tracks[0].sections[0].channels}
        self.assertEqual(channels["Location.X"].keys, [(0, -1000), (59, -500)])
        self.assertEqual(channels["Rotation.Z"].keys, [(0, 179), (59, 181)])
        self.assertFalse(self.u.actors)
        self.assertFalse(result["level_saved"])

    def test_cinematic_accepts_tick_quantization_but_rejects_frame_shift(self):
        from unittest.mock import patch
        def quantized(channel, frame, value, **kw):
            return NS(get_value=lambda: value, get_time=lambda **kw: NS(frame_number=NS(value=frame.value-1), sub_frame=.999))
        with patch.object(Channel, "add_key", quantized):
            result = self.run_editor({**cinematic(), "fps": 29})
        self.assertEqual(result["status"], "created_review_required", result)
        (self.folder / "receipt.json").unlink()
        def shifted(channel, frame, value, **kw):
            return NS(get_value=lambda: value, get_time=lambda **kw: NS(frame_number=NS(value=frame.value+1), sub_frame=0))
        with patch.object(Channel, "add_key", shifted):
            result = self.run_editor({**cinematic(), "destination": DEST+"Next"})
        self.assertEqual(result["error"], "camera_key_time_readback_failed")

    def test_unexpected_sequencer_channels_fail_without_saving(self):
        self.u.bad_channels = True
        result = self.run_editor(cinematic())
        self.assertEqual(result["error"], "unsupported_transform_channels")
        self.assertFalse(self.u.saved)

    def test_architecture_places_existing_meshes_without_saving_level(self):
        result = self.run_editor(architecture())
        self.assertEqual(result["status"], "placed_review_required", result)
        self.assertEqual(len(self.u.actors), 3)
        self.assertEqual(self.u.actors[1].location.y, 2200)
        self.assertEqual(self.u.actors[1].rotation.yaw, 100)
        self.assertIs(self.u.actors[0].component.properties["static_mesh"], self.u.objects[WALL])
        self.assertFalse(self.u.saved)
        self.assertFalse(result["level_saved"])

    def test_wrong_map_or_occupied_review_map_blocks_spawning(self):
        self.u.world.path = "/Game/Production.Production"
        result = self.run_editor(architecture())
        self.assertEqual(result["error"], "wrong_current_review_map")
        self.assertFalse(self.u.dirs)
        (self.folder / "receipt.json").unlink()
        self.u.world.path = MAP+".DirectorTest"
        self.u.actors.append(Obj("Existing", "Actor"))
        result = self.run_editor(architecture())
        self.assertEqual(result["error"], "review_map_not_empty")
        self.assertEqual(len(self.u.actors), 1)

    def test_failed_architecture_rolls_back_only_new_actors(self):
        self.u.fail_spawn_at = 1
        result = self.run_editor(architecture())
        self.assertEqual(result["error"], "module_spawn_failed")
        self.assertEqual(result["removed_actors"], ["Actor_0"])
        self.assertFalse(self.u.actors)
        self.assertFalse(result["level_saved"])

    def test_contact_import_recomputes_trace_and_requires_clean_measured_contact(self):
        from test_cryptonyan_animation import trace, settings
        spec = effects()
        spec["events"] = []
        config = settings(contact_space="world", contacts=[{"bone": "FootCustom", "start_s": 0, "end_s": 1}])
        binding = [{k: v for k, v in effects()["events"][0].items() if k not in ("id", "time_s", "kind")}]
        binding[0]["contact_id"] = "contact-000"
        result = import_contacts(trace(), config, spec, binding)
        self.assertEqual(result["events"][0]["time_s"], 0)
        self.assertEqual(result["events"][0]["origin"]["contact_status"], "within_threshold")
        with self.assertRaises(ValueError):
            import_contacts(trace(), {**config, "contact_space": "unknown"}, spec, binding)
        source = trace()
        source["samples"][1]["poses"]["FootCustom"]["position"][0] += .3
        with self.assertRaises(ValueError):
            import_contacts(source, config, spec, binding)

    def test_real_cli_offline_plan_dry_run_and_no_overwrite(self):
        path = self.folder / "recipe.json"
        write_json(path, cinematic())
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts/addons_core")}
        command = [sys.executable, "-m", "cryptonyan_asset_studio.creative_director", str(path),
                   "--project", str(self.project), "--output", str(self.folder / "plan.json")]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["operations"], 2)
        result = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio.unreal_director", str(self.folder / "plan.json"),
                                 "--report", str(self.folder / "dry.json")], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "planned")
        result = subprocess.run(command, env=env, capture_output=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
