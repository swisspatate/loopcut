# SPDX-License-Identifier: GPL-3.0-or-later
"""Surface feedback recipes/editor protocol and compiled engine-free runtime policy."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

import test_cryptonyan_director as fixtures
from cryptonyan_asset_studio.capabilities import route, guide
from cryptonyan_asset_studio.creative_director import recipe, make_plan, load_plan
from cryptonyan_asset_studio.game_project import GameProject
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.studio_service import StudioService
from cryptonyan_asset_studio.surface_feedback import TRACK
from cryptonyan_asset_studio.mcp_stdio import MCPServer
from cryptonyan_asset_studio.unreal_director import execute

ROOT = Path(__file__).resolve().parents[2]
SOUND = "/Game/Paw.Paw"
SOUND2 = "/Game/Paw2.Paw2"
SURFACE = "/Game/Stone.Stone"
ATTENUATION = "/Game/Near.Near"


def spec():
    return dict(kind="surface_feedback", destination=fixtures.DEST, animation=fixtures.ANIM,
                preview_mesh=fixtures.MESH, duration_s=1, foot_sockets=["PawL", "PawR"],
                events=[dict(id="Left", time_s=.25, socket="PawL", reviewed=True),
                        dict(id="Right", time_s=.75, socket="PawR", reviewed=True)],
                attenuation=ATTENUATION,
                settings=dict(trace_up_cm=15, trace_down_cm=45, contact_cooldown_seconds=.08,
                              event_cooldown_seconds=.2, min_contact_speed_cm_s=5,
                              hard_stop_seconds=3, max_active_sounds=8, max_active_effects=8),
                cues=[dict(id="StoneStep", event="contact", physical_material=SURFACE,
                           sounds=[SOUND,SOUND2], niagara=fixtures.FX, volume=[.2,1], pitch=[.9,1.1],
                           effect_scale=[.5,1], reference_speed_cm_s=600),
                      dict(id="Landing", event="landing", physical_material=None,
                           sounds=[SOUND], niagara=None, volume=[.2,1], pitch=[1,1],
                           effect_scale=[1,1], reference_speed_cm_s=1200)])


class FeedbackEditor(fixtures.Editor):
    CryptoNyanContactNotify = object
    CryptoNyanSurfaceFeedbackProfile = "CryptoNyanSurfaceFeedbackProfile"
    CryptoNyanSurfaceFeedbackCue = fixtures.Obj
    CryptoNyanFeedbackKind = NS(CONTACT="contact", JUMP="jump", LANDING="landing")
    DataAssetFactory = fixtures.Obj

    def __init__(self, root):
        super().__init__(root); self.profile_valid = True; self.fail_save_at = None; self.on_save = None

    def create(self, name, directory, kind, factory):
        assert kind == self.CryptoNyanSurfaceFeedbackProfile
        assert factory.get_editor_property("data_asset_class") == kind
        obj = fixtures.Obj(directory+"/"+name+"."+name, kind)
        obj.validate_profile = lambda:self.profile_valid
        self.objects[obj.path] = obj
        if self.on_create: self.on_create(obj)
        return obj

    def save(self, obj, **kwargs):
        if self.fail_save_at is not None and len(self.saved) == self.fail_save_at: return False
        result = super().save(obj, **kwargs)
        if self.on_save: self.on_save(obj)
        return result


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        fixtures.DirectorTests.setUp(self)
        self.u.__class__ = FeedbackEditor
        self.u.profile_valid = True; self.u.fail_save_at = None; self.u.on_save = None
        self.u.EditorAssetLibrary.save_loaded_asset = self.u.save
        self.u.sockets.add("PawR")
        for path in (SOUND,SOUND2): self.u.add(path,"SoundWave",duration=.2,looping=False,num_channels=1)
        self.u.add(SURFACE,"PhysicalMaterial"); self.u.add(ATTENUATION,"SoundAttenuation")
        self.report = self.folder/"receipt.json"

    plan = fixtures.DirectorTests.plan

    def run_editor(self, value=None, apply=True):
        return execute(self.plan(spec() if value is None else value),self.report,apply=apply,unreal_module=self.u)

    def test_plan_roundtrip_pins_all_source_packages_and_keeps_recipe_unchanged(self):
        value = spec(); before = copy.deepcopy(value); plan = make_plan(value,self.project)
        self.assertEqual(value,before); self.assertEqual(make_plan(value,self.project),plan)
        self.assertEqual(plan["source_classes"][SOUND],"SoundWave")
        self.assertEqual(plan["source_classes"][ATTENUATION],"SoundAttenuation")
        self.assertEqual(plan["source_classes"][SURFACE],"PhysicalMaterial")
        self.assertEqual(len(plan["sources"]),7); self.assertEqual(plan["operations"],value["events"])

    def test_dry_run_needs_no_plugin_and_does_not_create_assets(self):
        self.u.CryptoNyanContactNotify = None
        result = self.run_editor(apply=False)
        self.assertEqual(result["status"],"planned"); self.assertEqual(self.u.dirs,set()); self.assertEqual(self.u.saved,[])

    def test_profile_and_animation_candidates_keep_original_rig_and_notifies(self):
        original = copy.deepcopy(self.u.objects[fixtures.ANIM].properties)
        result = self.run_editor(); self.assertEqual(result["status"],"created_review_required",result)
        self.assertEqual(len(result["owned_assets"]),2); self.assertEqual(len(result["saved_assets"]),2)
        profile = self.u.objects[result["profile"]]; animation = self.u.objects[result["animation"]]
        self.assertEqual(profile.get_editor_property("target_mesh").path,fixtures.MESH)
        self.assertEqual(profile.get_editor_property("foot_sockets"),["PawL","PawR"])
        self.assertEqual(profile.get_editor_property("cues")[0].get_editor_property("physical_material").path,SURFACE)
        self.assertEqual([s.path for s in profile.get_editor_property("cues")[0].get_editor_property("sounds")],[SOUND,SOUND2])
        contacts = [n for n in animation.properties["notifies"] if n.track == TRACK]
        self.assertEqual([(n.time,n.notify.get_editor_property("foot_socket")) for n in contacts],[(.25,"PawL"),(.75,"PawR")])
        self.assertTrue(all(n.notify.get_editor_property("should_fire_in_editor") is False for n in contacts))
        self.assertEqual(self.u.objects[fixtures.ANIM].properties["tracks"],original["tracks"])
        self.assertEqual(len(self.u.objects[fixtures.ANIM].properties["notifies"]),1)
        for flag in ("engine_validated","component_installed","anim_blueprint_modified","audio_playback_validated","collision_validated"):
            self.assertFalse(result[flag])

    def test_jump_and_surface_fallback_cues_are_explicit(self):
        value = spec(); value["cues"][0]["event"] = "jump"; value["cues"][0]["physical_material"] = None
        result = self.run_editor(value); self.assertEqual(result["status"],"created_review_required")
        cue = self.u.objects[result["profile"]].get_editor_property("cues")[0]
        self.assertEqual(cue.get_editor_property("kind"),"jump"); self.assertIsNone(cue.get_editor_property("physical_material"))

    def test_niagara_only_profile_needs_no_attenuation_or_sound(self):
        value = spec(); value["attenuation"] = None; value["cues"] = value["cues"][:1]; value["cues"][0]["sounds"] = []
        result = self.run_editor(value); self.assertEqual(result["status"],"created_review_required",result)
        self.assertIsNone(self.u.objects[result["profile"]].get_editor_property("attenuation"))

    def test_closed_schema_and_bounded_settings(self):
        cases=[]
        for key,value in (("extra",True),("duration_s",float("nan")),("foot_sockets",["PawL","pawl"]),("events",[])):
            item=spec();item[key]=value;cases.append(item)
        for key,value in (("max_active_sounds",True),("max_active_effects",17),("hard_stop_seconds",6),
                          ("contact_cooldown_seconds",0),("trace_down_cm",float("inf"))):
            item=spec();item["settings"][key]=value;cases.append(item)
        for item in cases:
            with self.subTest(item=item),self.assertRaises(ValueError):make_plan(item,self.project)
        self.assertEqual(self.u.dirs,set())

    def test_contacts_require_real_mapped_names_reviewed_timings_and_no_duplicates(self):
        for change in (dict(socket="Unknown"),dict(reviewed=False),dict(time_s=1),dict(time_s=-1),dict(command="run")):
            value=spec();value["events"][0].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):recipe(value)
        for field in ("events","foot_sockets"):
            value=spec();value[field].append(copy.deepcopy(value[field][0]))
            with self.assertRaises(ValueError):recipe(value)

    def test_ambiguous_empty_or_unbounded_cues_are_rejected(self):
        cases=[]
        for change in (dict(event="cast"),dict(sounds=[SOUND,SOUND]),dict(volume=[1,0]),dict(pitch=[.1,1]),
                       dict(sounds=[],niagara=None),dict(physical_material=fixtures.ANIM),dict(reference_speed_cm_s=0)):
            value=spec();value["cues"][0].update(change);cases.append(value)
        value=spec();value["cues"].append(copy.deepcopy(value["cues"][0]));cases.append(value)
        value=spec();value["attenuation"]=None;cases.append(value)
        for value in cases:
            with self.subTest(value=value),self.assertRaises(ValueError):recipe(value)

    def test_mono_duration_and_nonlooping_are_checked_before_reserving_destination(self):
        wave=self.u.objects[SOUND]
        for field,value in (("num_channels",2),("duration",0),("duration",4),("duration",float("nan")),("looping",True)):
            before=wave.properties[field];wave.properties[field]=value
            result=self.run_editor();self.report.unlink();wave.properties[field]=before
            self.assertEqual(result["status"],"failed");self.assertEqual(self.u.dirs,set());self.assertEqual(result["owned_assets"],[])

    def test_missing_socket_plugin_or_wrong_asset_class_blocks_before_mutation(self):
        for case in ("socket","plugin","class"):
            with self.subTest(case=case):
                if case=="socket": self.u.sockets.remove("PawR")
                elif case=="plugin": self.u.CryptoNyanSurfaceFeedbackCue=None
                else: self.u.objects[SURFACE].kind="Material"
                result=self.run_editor();self.report.unlink()
                self.assertEqual(result["status"],"failed");self.assertEqual(self.u.dirs,set())
                self.u.sockets.add("PawR");self.u.CryptoNyanSurfaceFeedbackCue=fixtures.Obj;self.u.objects[SURFACE].kind="PhysicalMaterial"

    def test_source_with_directed_track_is_not_stacked_again(self):
        for track in (TRACK,"cn_directedeffects"):
            self.u.objects[fixtures.ANIM].properties["tracks"].append(track)
            result=self.run_editor();self.report.unlink();self.u.objects[fixtures.ANIM].properties["tracks"].remove(track)
            self.assertEqual(result["status"],"failed");self.assertEqual(self.u.dirs,set())

    def test_changed_source_or_sidecar_refuses_loaded_plan(self):
        path=self.plan(spec());source=self.project/"Content/Paw.uasset";original=source.read_bytes()
        source.write_bytes(b"changed")
        with self.assertRaises(ValueError):load_plan(path)
        source.write_bytes(original);sidecar=source.with_suffix(".ubulk");sidecar.write_bytes(b"added after plan")
        with self.assertRaises(ValueError):load_plan(path)

    def test_source_drift_during_creation_prevents_saves_and_preserves_partial_candidates(self):
        def drift(obj):(self.project/"Content/Paw.uasset").write_bytes(b"changed")
        self.u.on_create=drift;result=self.run_editor()
        self.assertEqual(result["status"],"failed");self.assertEqual(result["saved_assets"],[])
        self.assertEqual(len(result["owned_assets"]),2);self.assertIn(fixtures.DEST,self.u.dirs)

    def test_second_save_failure_retains_first_save_without_overwrite_or_cleanup(self):
        self.u.fail_save_at=1;result=self.run_editor()
        self.assertEqual(result["status"],"failed");self.assertEqual(len(result["saved_assets"]),1)
        self.assertEqual(len(result["owned_assets"]),2);self.report.unlink()
        result=self.run_editor();self.assertEqual(result["status"],"failed");self.assertEqual(result["owned_assets"],[])

    def test_source_drift_between_saves_prevents_saving_second_candidate(self):
        self.u.on_save=lambda obj:(self.project/"Content/Paw.uasset").write_bytes(b"changed after first save")
        result=self.run_editor();self.assertEqual(result["status"],"failed");self.assertEqual(len(result["saved_assets"]),1)

    def test_unsaved_foreign_content_between_saves_stops_the_second_save(self):
        self.u.on_save=lambda obj:self.u.dirty.append("/Game/Paw")
        result=self.run_editor();self.assertEqual(result["status"],"failed")
        self.assertEqual(len(result["saved_assets"]),1)
        self.assertEqual(result["error"],"save_content_changes_before_director_run")

    def test_runtime_profile_validator_and_property_readback_failures_are_recorded(self):
        self.u.profile_valid=False;result=self.run_editor()
        self.assertEqual(result["status"],"failed");self.assertEqual(result["saved_assets"],[])
        self.assertEqual(result["error"],"runtime_feedback_profile_validation_failed")

    def test_profile_cue_corruption_after_array_assignment_is_detected(self):
        setter=fixtures.Obj.set_editor_property
        def corrupt(obj,field,value):
            setter(obj,field,value)
            if field=="cues": value[0].properties["max_volume"]=.01
        with patch.object(fixtures.Obj,"set_editor_property",new=corrupt):result=self.run_editor()
        self.assertEqual(result["status"],"failed");self.assertEqual(result["error"],"feedback_cue_readback_failed")
        self.assertEqual(result["saved_assets"],[])

    def test_candidate_cannot_be_misreported_as_a_foreign_source_asset(self):
        self.u.AssetToolsHelpers=NS(get_asset_tools=lambda:NS(create_asset=lambda *args:self.u.objects[fixtures.MESH]))
        result=self.run_editor();self.assertEqual(result["status"],"failed")
        self.assertEqual(result["owned_assets"],[]);self.assertEqual(result["saved_assets"],[])

    def test_extra_asset_created_during_candidate_creation_blocks_publication(self):
        self.u.on_create=lambda obj:self.u.objects.setdefault(fixtures.DEST+"/Foreign.Foreign",fixtures.Obj(fixtures.DEST+"/Foreign.Foreign","Material"))
        result=self.run_editor();self.assertEqual(result["status"],"failed")
        self.assertEqual(result["error"],"unexpected_director_assets");self.assertEqual(result["saved_assets"],[])

    def test_plan_operations_cannot_be_changed_even_with_a_new_identity(self):
        path=self.plan(spec());plan=json.loads(path.read_text(encoding="utf-8"))
        plan["operations"][0]["time_s"]=.99
        from cryptonyan_asset_studio.unreal_material_variants import _hash
        plan["identity"]=_hash({k:v for k,v in plan.items() if k!="identity"});write_json(path,plan)
        with self.assertRaises(ValueError):load_plan(path)

    def test_existing_cli_contact_import_never_fabricates_measured_timings(self):
        from cryptonyan_asset_studio.creative_director import import_contacts
        # This recipe accepts reviewed contact times, not a detached approval flag
        # or unmeasured Unreal component-space contacts.
        with patch("cryptonyan_asset_studio.creative_director.audit_trace",return_value=dict(duration_s=1)):
            with self.assertRaises(ValueError):import_contacts({}, {}, spec(), [])

    def test_wrong_project_dirty_packages_and_existing_destination_are_refused(self):
        for case in ("dirty","occupied","project"):
            if case=="dirty": self.u.dirty=["/Game/Foreign"]
            elif case=="occupied": self.u.dirs.add(fixtures.DEST)
            else:self.u.Paths.project_dir=lambda:str(self.folder)
            result=self.run_editor();self.report.unlink();self.assertEqual(result["status"],"failed")
            self.assertEqual(result["owned_assets"],[]);self.u.dirty=[];self.u.dirs.clear()

    def test_cli_plan_and_dry_run_reuse_director_without_engine(self):
        source=self.folder/"recipe.json";plan=self.folder/"cli-plan.json";report=self.folder/"cli-result.json"
        write_json(source,spec());env={**os.environ,"PYTHONPATH":str(ROOT/"scripts/addons_core")}
        for module,args in (("creative_director",[str(source),"--project",str(self.project),"--output",str(plan)]),
                            ("unreal_director",[str(plan),"--report",str(report)])):
            result=subprocess.run([sys.executable,"-m","cryptonyan_asset_studio."+module,*args],capture_output=True,text=True,env=env,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"],"planned")

    def test_studio_plan_and_inert_unreal_handoff_preserve_existing_workflow(self):
        work=self.folder/"studio";assets=self.folder/"assets";assets.mkdir()
        service=StudioService(work,assets,project=GameProject(self.project))
        self.addCleanup(service.close)
        result=service.execute("feedback-plan","director_plan",dict(recipe=spec()))
        self.assertEqual(result["status"],"succeeded",result)
        handoff=service.execute("feedback-editor","unreal_handoff",dict(kind="director_review",plan=result["output"]+"/plan.json"))
        self.assertEqual(handoff["status"],"succeeded",handoff)
        data=json.loads(service.artifact("feedback-editor","result.json")["text"])
        self.assertFalse(data["editor_executed"])

    def test_natural_goal_routes_to_existing_director_family(self):
        self.assertEqual(route("Ajoute des sons de pas aux pattes de mon personnage")["primary"],"creative_director")
        self.assertIn("surface_feedback",str(guide("creative_director")))

    def test_mcp_guide_exposes_closed_recipe_schema_then_plans_without_editor(self):
        assets=self.folder/"mcp-assets";assets.mkdir()
        service=StudioService(self.folder/"mcp-work",assets,project=GameProject(self.project));self.addCleanup(service.close)
        server=MCPServer(None,project=service.project,studio=service)
        server.handle(dict(jsonrpc="2.0",id=0,method="initialize"))
        def call(tool,args):
            result=server.handle(dict(jsonrpc="2.0",id=1,method="tools/call",params=dict(name=tool,arguments=args)))["result"]
            self.assertFalse(result["isError"],result);return json.loads(result["content"][0]["text"])
        guide_value=call("studio_guide",dict(capability="creative_director"))
        schema=guide_value["surface_feedback_schema"]
        self.assertFalse(schema["additionalProperties"]);self.assertEqual(set(schema["required"]),set(spec()))
        result=call("studio_execute",dict(request_id="feedback",operation="director_plan",arguments=dict(recipe=spec())))
        self.assertEqual(result["status"],"succeeded")


class RuntimePolicyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("g++") or shutil.which("clang++"),"Standalone C++ compiler unavailable")
    def test_compiled_runtime_gate_variation_and_intensity_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/"feedback.cpp";binary=root/("feedback.exe" if os.name=="nt" else "feedback")
            source.write_text('''#include "CryptoNyanFeedbackRules.h"
#include <cassert>
#include <limits>
int main(){using namespace CryptoNyanFeedbackRules;
const CueKey cues[]={{0,0},{0,42},{2,0},{1,99}};
assert(Select(cues,4,0,42)==1);assert(Select(cues,4,0,17)==0);assert(Select(cues,4,2,42)==2);
assert(Select(cues,4,1,99)==3);assert(Select(cues,4,1,42)==-1);assert(Select(cues,4,0,0)==0);
assert(Select(nullptr,4,0,42)==-1);assert(Select(cues,33,0,42)==-1);assert(Select(cues,4,3,42)==-1);
assert(Intensity(0,600)==0);assert(Intensity(300,600)==.5);assert(Intensity(1200,600)==1);
assert(Intensity(std::numeric_limits<double>::quiet_NaN(),600)==0);
assert(Intensity(100,0)==0);assert(Intensity(-1,600)==0);
for(int n=1;n<=8;++n) for(int p=-1;p<n;++p) for(unsigned r=0;r<100;++r){
const int v=Variant(n,p,r);assert(v>=0&&v<n);if(n>1&&p>=0)assert(v!=p);}
assert(Variant(0,0,0)==-1);assert(Variant(9,0,0)==-1);
Gate a,b;assert(a.Admit(0,0,.08));assert(!a.Admit(0,0,.08));assert(a.Admit(1,0,.08));
assert(b.Admit(0,0,.08));assert(a.Admit(0,.1,.08));assert(!a.Admit(0,.09,.08));
assert(!a.Admit(-1,1,.08));assert(!a.Admit(10,1,.08));assert(!a.Admit(0,1,.001));
assert(!a.Admit(0,std::numeric_limits<double>::infinity(),.08));
Gate bucket;for(int i=0;i<8;++i)assert(bucket.Admit(i,0,.04));assert(!bucket.Admit(8,0,.04));
assert(bucket.Admit(8,1./24.+1e-6,.04));assert(!bucket.Admit(9,1./24.+1e-6,.04));
Gate landing;assert(landing.Admit(9,0,.2));assert(!landing.Admit(0,.01,.08));
assert(landing.Admit(0,.1,.08));assert(!landing.Admit(9,.1,.2));assert(landing.Admit(9,.3,.2));
Gate floats;assert(floats.Admit(0,0,double(.04f)));
Gate stress;int accepted=0;for(int i=0;i<10000;++i)if(stress.Admit(i%10,i*.001,.04))++accepted;
assert(accepted<=8+240);assert(!stress.Admit(0,-1,.08));
}''',encoding="utf-8")
            compiler=shutil.which("g++") or shutil.which("clang++")
            result=subprocess.run([compiler,"-std=c++17","-Wall","-Wextra","-Werror","-I",
                str(ROOT/"integrations/unreal/CryptoNyanRuntime/Source/CryptoNyanRuntime/Public"),str(source),"-o",str(binary)],
                capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=="__main__":unittest.main()
