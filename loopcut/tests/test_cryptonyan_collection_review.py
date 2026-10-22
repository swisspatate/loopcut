# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline gallery snapshots, source/origin guards and real MCP/HTTP wiring."""
import base64
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import test_cryptonyan_reference_collections as fixtures
from cryptonyan_asset_studio import collection_review as reviews
from cryptonyan_asset_studio.capabilities import route
from cryptonyan_asset_studio.game_project import GameProject
from cryptonyan_asset_studio.mcp_stdio import MCPServer, tool_list
from cryptonyan_asset_studio.png_pixels import encode
from cryptonyan_asset_studio.storage import digest, write_json
from cryptonyan_asset_studio.texture_collections import TextureCollections, requests_for
from test_cryptonyan_materials import png

ROOT = Path(__file__).resolve().parents[2]


class GalleryTests(unittest.TestCase):
    save = fixtures.ReferenceCollectionTests.save
    open = fixtures.ReferenceCollectionTests.open
    plan = fixtures.ReferenceCollectionTests.plan
    advance = fixtures.ReferenceCollectionTests.advance
    collect = fixtures.ReferenceCollectionTests.collect
    complete = fixtures.ReferenceCollectionTests.complete

    def setUp(self): fixtures.ReferenceCollectionTests.setUp(self)
    def review(self, review_id="first"): return self.project.collection_review("biome", review_id)
    def folder(self, review_id="first"): return self.service.root/"collection-reviews"/("review-"+review_id)
    def artifact(self, file="images/body-base_color.png", review_id="first"):
        return self.project.collection_review_artifact("biome", review_id, file)

    def test_complete_gallery_is_offline_preserves_sources_and_copies_exact_channels(self):
        self.complete(); calls = len(self.peer.calls)
        def snapshot(root):
            return {p.relative_to(root).as_posix(): None if p.suffix==".lock" else digest(p)
                    for p in root.rglob("*") if p.is_file()}
        before = {name: snapshot(self.service.root/name) for name in ("requests", "collections", "asset-bindings")}
        game = snapshot(self.game)
        with patch.object(self.service, "transport", side_effect=AssertionError("Gallery must not perform HTTP")):
            result = self.review(); self.assertEqual(self.review(), result)
        self.assertEqual(result["states"], {"collected": 2}); self.assertTrue(result["snapshot"])
        self.assertTrue(result["target_freshness_validated"]); self.assertFalse(result["reference_source_freshness_validated"])
        for item in result["items"]:
            relative = item["images"][0]["file"]
            source = self.service._folder(item["request_id"])/"result/material/base_color.png"
            self.assertEqual((self.folder()/relative).read_bytes(), source.read_bytes())
        self.assertEqual(before, {name: snapshot(self.service.root/name) for name in before})
        self.assertEqual(game, snapshot(self.game)); self.assertEqual(calls, len(self.peer.calls))

    def test_planned_and_partial_collections_do_not_collect_or_poll(self):
        self.plan(); planned = self.review("planned")
        self.assertEqual(planned["states"], {"planned": 2}); self.assertEqual(self.peer.calls, [])
        self.advance(); calls = len(self.peer.calls)
        pending = self.review("pending"); self.assertEqual(pending["states"], {"submitted": 1, "planned": 1})
        self.assertEqual(len(self.peer.calls), calls)
        self.collect(); partial = self.review("partial")
        self.assertEqual(partial["states"], {"collected": 1, "planned": 1})
        self.assertFalse((self.collections._folder("biome")/"index.json").exists())

    def test_same_review_id_keeps_captured_progress_and_new_id_captures_new_progress(self):
        self.plan(); first = self.review(); sha = digest(self.folder()/"index.html")
        self.complete()
        self.assertEqual(self.review(), first); self.assertEqual(digest(self.folder()/"index.html"), sha)
        self.assertEqual(self.review("latest")["states"], {"collected": 2})

    def test_partial_snapshot_keeps_prior_candidate_after_collection_advances(self):
        self.plan(); self.advance(); self.collect(); first = self.review()
        self.advance(); self.collect(); self.assertEqual(self.review(), first)
        self.assertEqual(self.review("complete")["states"], {"collected": 2})

    def test_request_ids_and_windows_reserved_review_ids_are_safe(self):
        self.plan(); result = self.review("con"); self.assertIn("review-con", result["gallery_file"])
        for value in ("../escape", "CON", "", None, "x"*41):
            with self.subTest(value=value), self.assertRaises(ValueError): self.review(value)
        with self.assertRaisesRegex(ValueError, "identity changed"):
            self.project.collection_review("other", "con")

    def test_native_mcp_artifact_image_matches_original_bytes(self):
        self.complete(); result = self.review(); image = self.artifact()
        self.assertEqual(base64.b64decode(image["data"]), (self.folder()/"images/body-base_color.png").read_bytes())
        server = MCPServer(None, textures=self.service, project=self.project)
        server.handle(dict(jsonrpc="2.0", id=0, method="initialize"))
        response = server.handle(dict(jsonrpc="2.0", id=1, method="tools/call", params=dict(
            name="project_collection_review_artifact", arguments=dict(collection_id="biome", review_id="first", file="images/body-base_color.png"))))
        self.assertFalse(response["result"]["isError"]); self.assertEqual(response["result"]["content"][0]["type"], "image")
        self.assertEqual(result["items"][0]["request_id"], requests_for(self.spec)[0]["request"]["request_id"])

    def test_text_artifacts_and_unknown_paths_respect_the_manifest(self):
        self.complete(); self.review(); self.assertIn("Revue des textures", self.artifact("index.html")["text"])
        metadata = json.loads(self.artifact("gallery.json")["text"])
        self.assertEqual(metadata["capture"]["items"][0]["inspection"]["reference_preparation"]["preparation_id"], "body-ref")
        for value in ("../request.json", "request.json", "review.json", "/etc/passwd", "images/missing.png"):
            with self.subTest(value=value), self.assertRaises(ValueError): self.artifact(value)

    def test_html_escapes_notes_and_has_no_scripts_remote_links_or_event_handlers(self):
        self.spec["style"] = '<script>alert("x")</script>'
        self.spec["items"][0]["description"] = '<img src="https://invalid" onerror="alert(1)">\r\ncafé'
        self.complete(); self.review(); page = (self.folder()/"index.html").read_text(encoding="utf-8")
        class Inspect(HTMLParser):
            def __init__(self): super().__init__(); self.tags = []
            def handle_starttag(self, tag, attrs): self.tags.append((tag, dict(attrs)))
        parser = Inspect(); parser.feed(page)
        self.assertIn("&lt;script&gt;", page); self.assertNotIn("script", [t for t, _ in parser.tags])
        self.assertIn("Content-Security-Policy", page)
        self.assertIn("\r\ncafé", self.artifact("index.html")["text"])
        for tag, attrs in parser.tags:
            self.assertFalse(any(key.startswith("on") for key in attrs))
            if tag == "img": self.assertTrue(attrs["src"].startswith("images/"))

    def test_changed_target_refuses_creation_reuse_and_artifact_read(self):
        self.complete(); self.review(); (self.game/"Content/Wall.uasset").write_bytes(b"changed")
        for method in (lambda: self.review("next"), self.review, self.artifact):
            with self.assertRaisesRegex(ValueError, "source changed"): method()
        self.assertFalse(self.folder("next").exists())

    def test_origin_candidate_or_request_changes_are_detected(self):
        self.complete(); self.review(); request = requests_for(self.spec)[0]["request"]["request_id"]
        for path in (self.project.bindings/(request+".candidate.json"), self.service._folder(request)/"request.json"):
            original = path.read_bytes(); value = json.loads(original)
            if "surface" in value: value["surface"] = "different"
            else: value["request"]["seed"] = 99
            write_json(path, value)
            with self.subTest(path=path), self.assertRaises(ValueError): self.artifact()
            path.write_bytes(original)

    def test_gallery_changed_bytes_extra_files_and_deleted_origin_are_refused(self):
        self.complete(); self.review(); image = self.folder()/"images/body-base_color.png"; original = image.read_bytes()
        image.write_bytes(png(width=3))
        with self.assertRaisesRegex(ValueError, "integrity"): self.artifact()
        image.write_bytes(original); extra = self.folder()/"extra.txt"; extra.write_text("extra", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "artifact set"): self.review()
        extra.unlink(); source = self.service._folder(requests_for(self.spec)[0]["request"]["request_id"])/"result/material/base_color.png"
        source.unlink()
        with self.assertRaises((ValueError, OSError)): self.artifact()

    def test_symlinked_gallery_images_are_refused(self):
        self.complete(); self.review(); image = self.folder()/"images/body-base_color.png"
        outside = self.root/"outside.png"; outside.write_bytes(image.read_bytes()); image.unlink()
        try: image.symlink_to(outside)
        except OSError: self.skipTest("Symlinks unavailable for this Windows account")
        with self.assertRaises(ValueError): self.artifact()

    def test_reference_sources_and_profiles_are_not_required_for_historical_review(self):
        self.complete(); self.review(); calls = len(self.peer.calls)
        shutil.rmtree(self.service.root/"reference-preparations"); shutil.rmtree(self.inputs)
        self.source.unlink(); self.second_source.unlink(); self.service.lock.close()
        self.catalog["profiles"] = []; self.save(); self.service = self.open()
        self.project = GameProject(self.game, self.service); self.collections = TextureCollections(self.project)
        self.assertEqual(self.review()["states"], {"collected": 2})
        self.assertEqual(self.artifact()["type"], "image"); self.assertEqual(self.review("new")["states"], {"collected": 2})
        self.assertEqual(len(self.peer.calls), calls)

    def test_image_and_aggregate_copy_limits_omit_without_resizing(self):
        self.complete()
        with patch.object(reviews, "IMAGE_COPY_LIMIT", 0): result = self.review("no-copy")
        self.assertTrue(all(i["images"][0]["omitted"] == "image_byte_limit" for i in result["items"]))
        self.assertEqual(self.review("no-copy"), result)
        first = self.service.inspect(requests_for(self.spec)[0]["request"]["request_id"])["channels"][0]["bytes"]
        with patch.object(reviews, "COPY_BUDGET", first): limited = self.review("one-copy")
        self.assertIsNotNone(limited["items"][0]["images"][0]["file"])
        self.assertEqual(limited["items"][1]["images"][0]["omitted"], "gallery_byte_limit")
        self.assertEqual(self.review("one-copy"), limited)

    def test_large_exact_html_images_do_not_bypass_the_native_mcp_image_limit(self):
        image = encode(1024, 1024, random.Random(7).randbytes(1024*1024*3)); self.assertGreater(len(image), 2*1024*1024)
        peer = self.peer
        self.service.transport = lambda method, path, payload=None, **kwargs: image if path.startswith("/view?") else peer(method, path, payload, **kwargs)
        self.complete(); result = self.review()
        self.assertEqual((self.folder()/"images/body-base_color.png").read_bytes(), image)
        self.assertFalse(next(a for a in result["artifacts"] if a["file"] == "images/body-base_color.png")["readable"])
        with self.assertRaisesRegex(ValueError, "2 MiB"): self.artifact()

    def test_drift_while_copying_keeps_an_incomplete_review_without_retry(self):
        self.complete(); original = reviews.read_png
        def change(path):
            result = original(path); (self.game/"Content/Wall.uasset").write_bytes(b"changed during copy"); return result
        with patch.object(reviews, "read_png", side_effect=change), self.assertRaisesRegex(ValueError, "source changed"): self.review()
        self.assertFalse((self.folder()/"review.json").exists())
        with self.assertRaisesRegex(ValueError, "incomplete"): self.review()

    def test_origin_drift_during_artifact_read_is_rechecked(self):
        self.complete(); self.review(); read = reviews.read_artifact
        def change(*args):
            result = read(*args); (self.game/"Content/Body.uasset").write_bytes(b"changed during read"); return result
        with patch.object(reviews, "read_artifact", side_effect=change), self.assertRaisesRegex(ValueError, "source changed"): self.artifact()

    def test_rehashed_page_and_channel_mapping_cannot_change_the_frozen_render(self):
        self.complete(); self.review(); folder = self.folder(); receipt = folder/"review.json"
        original = receipt.read_bytes(); page = folder/"index.html"; raw = page.read_bytes()
        page.write_bytes(raw+b"<script>bad()</script>"); record = json.loads(original)
        record["files"]["index.html"] = digest(page); write_json(receipt, record)
        with self.assertRaisesRegex(ValueError, "page changed"): self.review()
        page.write_bytes(raw); receipt.write_bytes(original)
        metadata = folder/"gallery.json"; value = json.loads(metadata.read_text(encoding="utf-8"))
        value["items"][0]["images"][0]["file"] = value["items"][1]["images"][0]["file"]
        write_json(metadata, value); record = json.loads(original); record["files"]["gallery.json"] = digest(metadata); write_json(receipt, record)
        with self.assertRaisesRegex(ValueError, "channel mapping"): self.review()

    def test_missing_or_corrupted_collection_index_is_not_repaired_by_review(self):
        self.complete(); path = self.collections._folder("biome")/"index.json"; original = path.read_bytes(); path.unlink()
        self.review(); self.assertFalse(path.exists())
        path.write_bytes(original); self.review("indexed"); path.unlink()
        with self.assertRaisesRegex(ValueError, "index changed"): self.review("indexed")
        path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "index integrity"): self.review("bad-index")
        self.assertEqual(path.read_text(encoding="utf-8"), "{}")

    def test_gallery_capacity_and_missing_collection_do_not_make_outputs(self):
        self.plan(); self.review()
        with patch.object(reviews, "MAX_REVIEWS", 1), self.assertRaisesRegex(ValueError, "capacity"): self.review("next")
        self.assertFalse(self.folder("next").exists())
        with self.assertRaises((ValueError, OSError)): self.project.collection_review("missing", "missing")
        self.assertFalse(self.folder("missing").exists())

    def test_cli_reviews_an_existing_collection_without_source_reference_roots(self):
        self.complete(); self.service.lock.close()
        result = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio.texture_collections", "--project", str(self.game),
            "--catalog", str(self.root/"profiles.json"), "--workspace", str(self.work/"textures"), "review", "biome", "cli"],
            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT/"scripts/addons_core")}, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr); data = json.loads(result.stdout)
        self.assertEqual(data["states"], {"collected": 2}); self.assertTrue(Path(data["gallery_file"]).is_file())

    def test_new_tools_are_exposed_only_with_project_and_textures(self):
        for config in ({}, dict(project=True), dict(textures=True)):
            self.assertNotIn("project_collection_review", [t["name"] for t in tool_list(**config)])
        self.assertEqual(len(tool_list(True, True, True, True)), 57)
        self.assertEqual(len(tool_list(textures=True, project=True)), 38)

    def test_gallery_goal_routes_to_the_existing_collection_family(self):
        self.assertEqual(route("Prépare une galerie de textures pour examiner mes assets")["primary"], "texture_collection")

    def test_copied_bytes_are_checked_against_the_original_before_publication(self):
        self.complete(); write = Path.write_bytes
        def corrupt(path, data):
            if path.parent.name == "images" and path.parent.parent == self.folder():
                data = png(width=3)
            return write(path, data)
        with patch.object(Path, "write_bytes", new=corrupt), self.assertRaisesRegex(ValueError, "integrity"): self.review()
        self.assertFalse((self.folder()/"review.json").exists())

    def test_uncollected_snapshot_cannot_change_the_bound_target(self):
        self.plan(); self.review(); path = self.folder()/"review.json"
        record = json.loads(path.read_text(encoding="utf-8")); record["capture"]["items"][0]["target"] = "Content/Other.uasset"
        write_json(path, record)
        with self.assertRaisesRegex(ValueError, "differs from the plan"): self.review()

    def test_all_declared_pbr_channels_keep_their_names_dimensions_and_color_spaces(self):
        self.service.lock.close()
        roles = ("base_color", "roughness", "metallic", "normal")
        self.profile["outputs"] = {role: ["6", index] for index, role in enumerate(roles)}
        self.save(); self.service = self.open(); self.project = GameProject(self.game, self.service)
        self.collections = TextureCollections(self.project)
        for item, source in zip(self.spec["items"], (self.source, self.second_source)):
            item["preparation_id"] += "-pbr"
            self.service.reference_prepare("rock", item["preparation_id"], {"reference": "asset:"+source.name})
        peer = self.peer
        def pbr(method, path, payload=None, **kwargs):
            if path.startswith("/view?"):
                for role, color in (("roughness", (127,)*3), ("metallic", (0,)*3), ("normal", (128,128,255))):
                    if "-"+role+".png" in path: return png(rgb=color)
            raw = peer(method, path, payload, **kwargs)
            if path.startswith("/history/"):
                value = json.loads(raw)
                for job in value.values():
                    images = job["outputs"]["6"]["images"]; first = images[0]
                    images += [{**first, "filename": first["filename"][:-4]+"-"+role+".png"} for role in roles[1:]]
                return json.dumps(value).encode()
            return raw
        self.service.transport = pbr; self.complete(); result = self.review()
        self.assertEqual(len(result["artifacts"]), 10)
        for item in result["items"]:
            self.assertEqual({image["channel"] for image in item["images"]}, set(roles))
            for image in item["images"]:
                self.assertEqual((image["width"], image["height"]), (2,2))
                self.assertEqual(image["color_space"], "sRGB" if image["channel"] == "base_color" else "Non-Color")
                self.assertEqual(digest(self.folder()/image["file"]), image["sha256"])

    def test_actual_stdio_http_generates_collection_and_reads_the_offline_gallery(self):
        peer = self.peer
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self): self.respond()
            def do_POST(self): self.respond(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            def respond(self, payload=None):
                data = peer(self.command, self.path, payload); self.send_response(200)
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            def log_message(self, *args): pass
        try: http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except PermissionError:
            if os.environ.get("CI"): raise
            self.skipTest("Sockets unavailable locally; actual gallery MCP/HTTP is mandatory in CI")
        thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        self.catalog["endpoint"] = "http://127.0.0.1:"+str(http.server_port); self.save()
        calls = [("texture_reference_prepare", dict(profile="rock", preparation_id=i, references={"reference": "asset:"+p.name}))
                 for i, p in (("body-ref", self.source), ("wall-ref", self.second_source))]
        calls += [("project_collection_plan", dict(specification=self.spec))]
        for _ in self.spec["items"]:
            calls += [("project_collection_advance", dict(collection_id="biome")), ("project_collection_collect", dict(collection_id="biome"))]
        calls += [("project_collection_review", dict(collection_id="biome", review_id="first")),
                  ("project_collection_review_artifact", dict(collection_id="biome", review_id="first", file="index.html")),
                  ("project_collection_review_artifact", dict(collection_id="biome", review_id="first", file="images/body-base_color.png"))]
        messages = [dict(jsonrpc="2.0", id=0, method="initialize")]+[
            dict(jsonrpc="2.0", id=n+1, method="tools/call", params=dict(name=name, arguments=args)) for n, (name, args) in enumerate(calls)]
        try:
            result = subprocess.run([sys.executable, "-m", "cryptonyan_asset_studio", "--workspace", str(self.root/"cli"),
                "--asset-root", str(self.assets), "--game-project", str(self.game), "--comfy-profiles", str(self.root/"profiles.json"), "serve"],
                input="".join(json.dumps(m)+"\n" for m in messages), capture_output=True, text=True,
                env={**os.environ, "PYTHONPATH": str(ROOT/"scripts/addons_core")}, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            responses = [json.loads(line) for line in result.stdout.splitlines()]; self.assertEqual(len(responses), len(messages))
            for r in responses[1:]: self.assertFalse(r["result"]["isError"], r)
            summary = json.loads(responses[-3]["result"]["content"][0]["text"])
            self.assertEqual(summary["states"], {"collected": 2}); self.assertFalse(summary["network_performed"])
            self.assertEqual(responses[-1]["result"]["content"][0]["type"], "image")
            self.assertEqual(len([c for c in self.peer.calls if c[0] == "POST"]), 2)
        finally:
            http.shutdown(); http.server_close(); thread.join(timeout=5)


if __name__ == "__main__": unittest.main()
