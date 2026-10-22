# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline, immutable texture collection galleries; copied PNGs are never resized."""
import hashlib
import html

from .artifact_io import IMAGE_LIMIT, TEXT_LIMIT, read_artifact
from .comfy_profiles import _read
from .comfyui_adapter import workflow_digest
from .materials import read_png
from .storage import digest, safe_path, write_json
from .texture_collections import _id

IMAGE_COPY_LIMIT = 8*1024*1024
COPY_BUDGET = 64*1024*1024
METADATA_LIMIT = 1024*1024
MAX_FILES = 66
MAX_REVIEWS = 128


def image_manifest(capture, copy_limit, budget):
    if (type(copy_limit) is not int or not 0 <= copy_limit <= IMAGE_COPY_LIMIT or
            type(budget) is not int or not 0 <= budget <= COPY_BUDGET):
        raise ValueError("Invalid collection gallery copy limits")
    items = []
    for item in capture["items"]:
        entry = {"id": item["id"], "state": item["state"], "images": []}
        for channel in item.get("inspection", {}).get("channels", []):
            image = {**channel, "file": None}
            if channel["bytes"] > copy_limit:
                image["omitted"] = "image_byte_limit"
            elif channel["bytes"] > budget:
                image["omitted"] = "gallery_byte_limit"
            else:
                budget -= channel["bytes"]
                image["file"] = "images/"+item["id"]+"-"+channel["channel"]+".png"
            entry["images"].append(image)
        items.append(entry)
    return items


class CollectionReview:
    def __init__(self, collections):
        self.collections = collections
        self.textures = collections.textures
        self.root = safe_path(self.textures.root, "collection-reviews")

    def folder(self, review_id):
        return safe_path(self.root, "review-"+_id(review_id))

    def _capture(self, plan, frozen=None):
        collection = self.collections
        collection._verify_sources(plan)
        items = []
        for index, item in enumerate(plan["items"]):
            row = collection._state(plan, item)
            prior = frozen["items"][index] if frozen else None
            if prior is not None and prior["state"] != "collected":
                expected = {key: item["request"][key] for key in ("request_id", "target", "seed", "surface")}
                expected.update(id=item["id"], description=plan["specification"]["items"][index]["description"])
                if (prior["state"] not in ("planned", "prepared", "submitted", "incomplete") or
                        any(prior.get(key) != value for key, value in expected.items()) or
                        prior.get("reference_preparation") != item["request"].get("reference_preparation") or
                        "inspection" in prior or "origin" in prior):
                    raise ValueError("Collection gallery captured item differs from the plan")
                # Keep the captured state even if the collection has since advanced.
                items.append(prior)
                continue
            entry = {**row, "surface": item["request"]["surface"],
                     "description": plan["specification"]["items"][index]["description"]}
            if row["state"] == "collected":
                # Only collected rows reach _candidate: this branch cannot collect or submit.
                collection._candidate(plan, item)
                review = self.textures.inspect(row["request_id"])
                folder = self.textures._folder(row["request_id"])
                entry["inspection"] = {key: review[key] for key in (
                    "profile", "prompt", "seed", "prompt_id", "template_sha256", "workflow_sha256",
                    "channels", "references", "reference_preparation", "models_declared")}
                entry["origin"] = {
                    "request_sha256": digest(safe_path(folder, "request.json")),
                    "texture_sha256": digest(safe_path(folder, "result/texture.json")),
                    "candidate_sha256": digest(safe_path(collection.project.bindings, row["request_id"]+".candidate.json"))}
            elif prior is not None:
                raise ValueError("A captured collection result is no longer collected")
            items.append(entry)
        index_path = safe_path(collection._folder(plan["specification"]["collection_id"]), "index.json")
        index_sha = None
        if index_path.exists():
            if _read(index_path) != collection._index(plan):
                raise ValueError("Collection index integrity failed; gallery refused")
            index_sha = digest(index_path)
        if frozen and frozen["index_sha256"] is not None and index_sha != frozen["index_sha256"]:
            raise ValueError("Captured collection index changed")
        collection._verify_sources(plan)
        return dict(collection_id=plan["specification"]["collection_id"], plan_sha256=workflow_digest(plan),
                    profile=plan["specification"]["profile"], style=plan["specification"]["style"], items=items,
                    index_sha256=frozen["index_sha256"] if frozen else index_sha,
                    reference_source_freshness_validated=False, visual_quality_validated=False,
                    gpu_execution_validated=False, model_provenance_verified=False,
                    distribution_approved=False, applied_to_game=False)

    def _files(self, folder, files):
        if (not isinstance(files, dict) or not 2 <= len(files) <= MAX_FILES or
                not {"index.html", "gallery.json"} <= set(files) or
                any(p not in ("index.html", "gallery.json") and not p.startswith("images/") for p in files)):
            raise ValueError("Invalid collection gallery file manifest")
        total = 0
        for relative, expected in files.items():
            path = safe_path(folder, relative); size = path.stat().st_size
            if size > (IMAGE_COPY_LIMIT if relative.endswith(".png") else METADATA_LIMIT):
                raise ValueError("Collection gallery artifact exceeds its byte limit")
            total += size
            if total > COPY_BUDGET+2*METADATA_LIMIT or digest(path) != expected:
                raise ValueError("Collection gallery integrity failed")
        actual = set()
        for path in folder.rglob("*"):
            relative = path.relative_to(folder).as_posix(); safe_path(folder, relative)
            if path.is_file() and relative not in ("request.json", "review.json"):
                actual.add(relative)
            if len(actual) > MAX_FILES:
                raise ValueError("Collection gallery file budget exceeded")
        if actual != set(files):
            raise ValueError("Collection gallery artifact set changed")

    def verified(self, collection_id, review_id):
        folder = self.folder(review_id)
        if not safe_path(folder, "review.json").is_file():
            raise ValueError("Gallery incomplete or missing; inspect locally before choosing another review ID")
        request = _read(safe_path(folder, "request.json"))
        record = _read(safe_path(folder, "review.json"))
        if (request != dict(collection_id=collection_id, review_id=review_id) or
                record.get("schema") != "cryptonyan.collection-review/1" or
                record.get("request_sha256") != workflow_digest(request)):
            raise ValueError("Collection gallery request identity changed")
        plan = self.collections._load(collection_id)
        captured = record["capture"]
        if captured["plan_sha256"] != workflow_digest(plan) or len(captured["items"]) != len(plan["items"]):
            raise ValueError("Collection gallery plan changed")
        if self._capture(plan, captured) != captured:
            raise ValueError("Collection gallery origin or captured metadata changed")
        self._files(folder, record["files"])
        gallery = _read(safe_path(folder, "gallery.json"), METADATA_LIMIT)
        if gallery["capture"] != captured or gallery["schema"] != "cryptonyan.collection-gallery/1":
            raise ValueError("Collection gallery metadata changed")
        if gallery["items"] != image_manifest(captured, gallery["image_byte_limit"], gallery["image_total_budget"]):
            raise ValueError("Collection gallery channel mapping changed")
        expected_files = {"index.html", "gallery.json"} | {image["file"] for item in gallery["items"]
                         for image in item["images"] if image["file"] is not None}
        if set(record["files"]) != expected_files:
            raise ValueError("Collection gallery image set changed")
        for item in gallery["items"]:
            for image in item.get("images", []):
                if image.get("file") is not None and record["files"].get(image["file"]) != image["sha256"]:
                    raise ValueError("Collection gallery image mapping changed")
        if safe_path(folder, "index.html").read_bytes() != render(gallery).encode("utf-8"):
            raise ValueError("Collection gallery page changed")
        self.collections._verify_sources(plan)
        return folder, record, gallery

    def summary(self, folder, record, gallery):
        states = {}
        for item in record["capture"]["items"]: states[item["state"]] = states.get(item["state"], 0)+1
        artifacts = []
        for relative, sha in record["files"].items():
            path = safe_path(folder, relative); size = path.stat().st_size
            artifacts.append(dict(file=relative, sha256=sha, bytes=size,
                readable=size <= (IMAGE_LIMIT if relative.endswith(".png") else TEXT_LIMIT)))
        items = [dict(id=item["id"], request_id=item["request_id"], state=item["state"],
                      images=displayed["images"]) for item, displayed in zip(record["capture"]["items"], gallery["items"])]
        return dict(collection_id=record["capture"]["collection_id"], review_id=folder.name.removeprefix("review-"),
                    snapshot=True, states=states, gallery_file=str(folder/"index.html"),
                    gallery_manifest=str(folder/"gallery.json"), artifacts=artifacts, items=items,
                    target_freshness_validated=True, reference_source_freshness_validated=False,
                    network_performed=False, visual_quality_validated=False, applied_to_game=False)

    def create(self, collection_id, review_id):
        _id(collection_id); folder = self.folder(review_id)
        if folder.exists():
            return self.summary(*self.verified(collection_id, review_id))
        if self.root.exists() and sum(1 for _ in self.root.iterdir()) >= MAX_REVIEWS:
            raise ValueError("Collection gallery capacity reached")
        plan = self.collections._load(collection_id); capture = self._capture(plan)
        self.root.mkdir(exist_ok=True, mode=0o700); folder.mkdir(mode=0o700)
        request = dict(collection_id=collection_id, review_id=review_id)
        write_json(folder/"request.json", request)
        items = image_manifest(capture, IMAGE_COPY_LIMIT, COPY_BUDGET)
        for item, displayed in zip(capture["items"], items):
            for channel, image in zip(item.get("inspection", {}).get("channels", []), displayed["images"]):
                if image["file"] is not None:
                    source = safe_path(self.textures._folder(item["request_id"])/"result", channel["file"])
                    data, _ = read_png(source)
                    if len(data) != channel["bytes"] or hashlib.sha256(data).hexdigest() != channel["sha256"]:
                        raise ValueError("Collected image changed during gallery copy")
                    destination = safe_path(folder, image["file"]); destination.parent.mkdir(exist_ok=True)
                    destination.write_bytes(data)
        gallery = dict(schema="cryptonyan.collection-gallery/1", capture=capture, items=items,
                       image_byte_limit=IMAGE_COPY_LIMIT, image_total_budget=COPY_BUDGET)
        write_json(folder/"gallery.json", gallery)
        (folder/"index.html").write_bytes(render(gallery).encode("utf-8"))
        files = {p.relative_to(folder).as_posix(): digest(p) for p in folder.rglob("*")
                 if p.is_file() and p.name != "request.json"}
        for item in items:
            for image in item["images"]:
                if image["file"] is not None: files[image["file"]] = image["sha256"]
        self._files(folder, files)
        if (_read(folder/"gallery.json", METADATA_LIMIT) != gallery or
                (folder/"index.html").read_bytes() != render(gallery).encode("utf-8")):
            raise ValueError("Collection gallery changed during publication")
        if self._capture(plan, capture) != capture:
            raise ValueError("Collection changed during gallery capture")
        record = dict(schema="cryptonyan.collection-review/1", request_sha256=workflow_digest(request), capture=capture, files=files)
        write_json(folder/"review.json", record)
        return self.summary(folder, record, gallery)

    def artifact(self, collection_id, review_id, file):
        folder, record, _ = self.verified(collection_id, review_id)
        artifacts = [dict(file=p, sha256=sha, bytes=safe_path(folder, p).stat().st_size) for p, sha in record["files"].items()]
        result = read_artifact(folder, artifacts, file, lambda p: str(p))
        self.verified(collection_id, review_id)
        return result


def render(gallery):
    """Static local page: fixed image paths, escaped data, no JS, remote links or fonts."""
    esc = lambda value: html.escape(str(value), quote=True)
    capture = gallery["capture"]; cards = []
    labels = dict(base_color="Couleur", roughness="Rugosité", metallic="Métallique", normal="Normale")
    states = dict(planned="Planifiée", prepared="À envoyer", submitted="Envoyée", collected="Collectée", incomplete="À vérifier")
    for item, displayed in zip(capture["items"], gallery["items"]):
        images = []
        for image in displayed["images"]:
            caption = esc(labels[image["channel"]])+" · "+str(image["width"])+" × "+str(image["height"])+" · "+esc(image["color_space"])
            picture = ('<img loading="lazy" alt="'+esc(image["channel"])+ '" src="'+esc(image["file"])+'">'
                       if image["file"] else '<p>Image originale conservée dans le dossier de résultat ; limite de copie atteinte.</p>')
            images.append('<figure>'+picture+'<figcaption>'+caption+'</figcaption></figure>')
        inspection = item.get("inspection", {}); preparation = inspection.get("reference_preparation")
        sources = preparation["sources"] if preparation else inspection.get("references", [])
        refs = ''.join('<li>'+esc(s["role"])+" · "+esc(s.get("handle", s.get("file", "")))+" · "+esc(s["sha256"])+"</li>" for s in sources)
        details = '<details><summary>Détails de génération et références</summary><p>Profil '+esc(capture["profile"])+" · seed "+esc(item["seed"])+" · demande "+esc(item["request_id"])+"</p><ul>"+refs+"</ul></details>"
        cards.append('<article><h2>'+esc(item["id"])+" · "+esc(item["surface"])+"</h2><p>"+esc(item["target"])+"</p><p>"+esc(item["description"])+"</p><p>État capturé : "+esc(states[item["state"]])+"</p><div class=maps>"+''.join(images)+"</div>"+details+"</article>")
    return ('<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\' file:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
        '<title>Revue des textures · '+esc(capture["collection_id"])+'</title><style>'
        'body{font:16px system-ui;background:#111827;color:#e5e7eb;margin:2rem}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}'
        'article{padding:1rem;background:#1f2937;border-radius:12px;overflow-wrap:anywhere}.maps{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem}'
        'figure{margin:0}img{width:100%;height:auto;background:#374151}figcaption,details{font-size:.85rem}summary{cursor:pointer}h1,h2{color:#fff}</style>'
        '<h1>Textures · '+esc(capture["collection_id"])+'</h1><p>'+esc(capture["style"])+ '</p>'
        '<p>Instantané local du lot. Images copiées sans redimensionnement. Examiner les UV, les surfaces et le rendu sur les copies du jeu avant adoption.</p>'
        '<main>'+''.join(cards)+'</main></html>')
