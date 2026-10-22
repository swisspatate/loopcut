# SPDX-License-Identifier: GPL-3.0-or-later
"""Closed surface-feedback recipes for the existing Director plan/handoff pipeline."""
from .animation_doctor import exact, name, number
from .creative_director import identifier, integer, rows, destination
from .unreal_material_variants import _object_path

SETTINGS = dict(trace_up_cm=(1,100), trace_down_cm=(1,200),
                contact_cooldown_seconds=(.04,1), event_cooldown_seconds=(.04,1),
                min_contact_speed_cm_s=(0,1000), hard_stop_seconds=(.05,5),
                max_active_sounds=(1,16), max_active_effects=(1,16))
PAIRS = dict(volume=(0,1), pitch=(.5,2), effect_scale=(.01,3))
EVENTS = ("contact", "jump", "landing")
TRACK = "CN_SurfaceContacts"


def validate(value):
    exact(value, ("kind", "destination", "animation", "preview_mesh", "duration_s", "foot_sockets",
                  "events", "settings", "attenuation", "cues"))
    if value["kind"] != "surface_feedback": raise ValueError("Expected surface_feedback recipe")
    destination(value["destination"])
    value["animation"] = _object_path(value["animation"])
    value["preview_mesh"] = _object_path(value["preview_mesh"])
    duration = number(value["duration_s"], .001, 600)
    feet = rows(value["foot_sockets"], 8)
    for foot in feet: name(foot)
    if len({f.casefold() for f in feet}) != len(feet): raise ValueError("Foot sockets must be distinct")
    exact(value["settings"], SETTINGS)
    for key, bounds in SETTINGS.items():
        (integer if key.startswith("max_active_") else number)(value["settings"][key], *bounds)
    if value["attenuation"] is not None: value["attenuation"] = _object_path(value["attenuation"])
    ids, triggers = set(), set()
    for event in rows(value["events"], 64):
        exact(event, ("id", "time_s", "socket", "reviewed"))
        identity = identifier(event["id"]).casefold(); name(event["socket"])
        number(event["time_s"], 0, duration)
        trigger = (round(event["time_s"], 6), event["socket"].casefold())
        if (identity in ids or trigger in triggers or event["time_s"] >= duration or event["reviewed"] is not True or
                event["socket"] not in feet):
            raise ValueError("Require distinct reviewed contacts before clip end and exact mapped foot sockets")
        ids.add(identity); triggers.add(trigger)
    value["events"].sort(key=lambda e:(e["time_s"], e["id"]))
    ids, keys = set(), set()
    for cue in rows(value["cues"], 32):
        exact(cue, ("id", "event", "physical_material", "sounds", "niagara", "volume", "pitch",
                    "effect_scale", "reference_speed_cm_s"))
        identity = identifier(cue["id"]).casefold()
        if cue["event"] not in EVENTS or identity in ids: raise ValueError("Invalid or duplicate feedback cue")
        ids.add(identity)
        if cue["physical_material"] is not None: cue["physical_material"] = _object_path(cue["physical_material"])
        key = (cue["event"], (cue["physical_material"] or "").casefold())
        if key in keys: raise ValueError("One cue per event/physical material; null is the explicit fallback")
        keys.add(key)
        if not isinstance(cue["sounds"], list) or len(cue["sounds"]) > 8: raise ValueError("At most eight sound variants")
        cue["sounds"] = [_object_path(p) for p in cue["sounds"]]
        if len({p.casefold() for p in cue["sounds"]}) != len(cue["sounds"]): raise ValueError("Sound variants must be distinct")
        if cue["niagara"] is not None: cue["niagara"] = _object_path(cue["niagara"])
        if not cue["sounds"] and cue["niagara"] is None: raise ValueError("A feedback cue needs sound or Niagara")
        if cue["sounds"] and value["attenuation"] is None: raise ValueError("Spatial sounds require an explicit attenuation asset")
        for key, bounds in PAIRS.items():
            pair = cue[key]
            if not isinstance(pair, list) or len(pair) != 2: raise ValueError("Expected a bounded min/max pair")
            number(pair[0], *bounds); number(pair[1], pair[0], bounds[1])
        number(cue["reference_speed_cm_s"], 1, 5000)
    # A single asset cannot silently occupy incompatible source classes.
    assets(value)
    return value


def assets(spec):
    refs = {}
    def add(path, kind):
        if path is None: return
        if path.casefold() in {p.casefold() for p in refs}:
            old = next(p for p in refs if p.casefold() == path.casefold())
            if old != path or refs[old] != kind: raise ValueError("Conflicting feedback asset roles or path case")
        refs[path] = kind
    add(spec["animation"], "AnimSequence"); add(spec["preview_mesh"], "SkeletalMesh")
    add(spec["attenuation"], "SoundAttenuation")
    for cue in spec["cues"]:
        add(cue["physical_material"], "PhysicalMaterial"); add(cue["niagara"], "NiagaraSystem")
        for sound in cue["sounds"]: add(sound, "SoundWave")
    if len(refs) > 128: raise ValueError("Feedback exceeds 128 explicit source assets")
    return refs


def schema():
    """Expose the actual input structure in studio_guide; sources/timings are never inferred."""
    def obj(properties):
        return dict(type="object",additionalProperties=False,required=list(properties),properties=properties)
    def array(item,low,high): return dict(type="array",minItems=low,maxItems=high,items=item)
    asset = dict(type="string",pattern=r"^/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?$")
    nullable = dict(anyOf=[asset,dict(type="null")])
    identity = dict(type="string",pattern=r"^[A-Za-z][A-Za-z0-9_]{0,47}$")
    foot = dict(type="string",minLength=1,maxLength=128)
    pairs = {key:dict(type="array",minItems=2,maxItems=2,items=dict(type="number",minimum=low,maximum=high))
             for key,(low,high) in PAIRS.items()}
    return obj(dict(kind=dict(type="string",enum=["surface_feedback"]),
        destination=dict(type="string",pattern=r"^/Game/CryptoNyan/DirectedReviews/[A-Za-z][A-Za-z0-9_]{0,47}$"),
        animation=asset,preview_mesh=asset,duration_s=dict(type="number",minimum=.001,maximum=600),
        foot_sockets=array(foot,1,8),attenuation=nullable,
        settings=obj({key:dict(type="integer" if key.startswith("max_active_") else "number",minimum=low,maximum=high)
                      for key,(low,high) in SETTINGS.items()}),
        events=array(obj(dict(id=identity,time_s=dict(type="number",minimum=0,exclusiveMaximum=600),
                              socket=foot,reviewed=dict(type="boolean",enum=[True]))),1,64),
        cues=array(obj(dict(id=identity,event=dict(type="string",enum=list(EVENTS)),physical_material=nullable,
                            sounds=array(asset,0,8),niagara=nullable,**pairs,
                            reference_speed_cm_s=dict(type="number",minimum=1,maximum=5000))),1,32)))
