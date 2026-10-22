# SPDX-License-Identifier: GPL-3.0-or-later
"""Scripted HTTP protocol tests, not claims of GPU/model execution."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.comfyui_adapter import ComfyUIClient, ComfyError, LocalHTTP, workflow_digest
from test_cryptonyan_materials import png


class Peer:
    def __init__(self):
        self.calls, self.identity = [], None
        self.state, self.output = "queued", {"filename": "result.png", "subfolder": "", "type": "output"}
        self.image = png()
        self.fail_submit = False

    def __call__(self, method, path, payload=None, **kwargs):
        self.calls.append((method, path, payload))
        if path == "/prompt":
            self.identity = payload["prompt_id"]
            if self.fail_submit:
                raise ComfyError("uncertain")
            result = {"prompt_id": self.identity, "node_errors": {}}
        elif path.startswith("/history/"):
            result = {} if self.state in ("queued", "running", "unknown") else {
                self.identity: {"status": {"completed": True, "status_str": "success" if self.state == "succeeded" else "error",
                                         "messages": [["execution_interrupted", {}]] if self.state == "cancelled" else []},
                                "outputs": {"9": {"images": [self.output]}}}}
        elif path == "/queue" and method == "POST":
            self.state = "unknown"
            return b""
        elif path == "/queue":
            result = {"queue_running": [[0, self.identity]] if self.state == "running" else [],
                      "queue_pending": [[0, self.identity]] if self.state == "queued" else []}
        elif path.startswith("/view?"):
            return self.image
        else:
            raise AssertionError(path)
        return json.dumps(result).encode()


class ComfyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workflow = {"3": {"class_type": "KSampler", "inputs": {"seed": 0}}}
        self.config = {"endpoint": "http://127.0.0.1:8188", "workflow_sha256": workflow_digest(self.workflow),
                       "seed_inputs": [["3", "seed"]], "models": []}
        self.peer = Peer()
        self.client = ComfyUIClient(self.config, self.root / "jobs", transport=self.peer)
        self.addCleanup(self.client.lock.close)

    def submit(self):
        return self.client.submit_workflow(self.workflow, seed=42)

    def test_hash_approval_before_submission(self):
        changed = copy.deepcopy(self.workflow)
        changed["3"]["class_type"] = "UnapprovedNode"
        with self.assertRaises(ComfyError):
            self.client.submit_workflow(changed, seed=42)
        self.assertEqual(self.peer.calls, [])

    def test_seed_application_and_durable_receipt(self):
        identity = self.submit()
        job = self.client._job(identity)
        self.assertEqual(job["workflow"]["3"]["inputs"]["seed"], 42)
        self.assertEqual(self.workflow["3"]["inputs"]["seed"], 0)
        self.assertNotEqual(job["workflow_sha256"], job["approved_workflow_sha256"])
        self.assertFalse(job["model_provenance_verified"])
        self.assertFalse(job["distribution_approved"])
        self.client.lock.close()
        with ComfyUIClient(self.config, self.root / "jobs", transport=self.peer) as resumed:
            self.assertEqual(resumed.poll_status(identity), "queued")

    def test_all_statuses(self):
        identity = self.submit()
        for state in ("queued", "running", "succeeded", "failed", "cancelled", "unknown"):
            self.peer.state = state
            self.assertEqual(self.client.poll_status(identity), state)

    def test_unknown_identity_cannot_control_job(self):
        self.submit()
        for identity in ("../../outside", "00000000-0000-0000-0000-000000000000"):
            with self.assertRaises((ValueError, FileNotFoundError)):
                self.client.cancel(identity)
        self.assertEqual(len(self.peer.calls), 1)

    def test_queue_cancel_is_targeted_and_never_interrupts(self):
        identity = self.submit()
        self.client.cancel(identity)
        self.assertIn(("POST", "/queue", {"delete": [identity]}), self.peer.calls)
        self.assertEqual(self.client.poll_status(identity), "unknown")
        self.assertTrue(self.client._job(identity)["queue_removal_requested"])
        self.assertFalse(any(path == "/interrupt" for _, path, _ in self.peer.calls))

    def test_running_cancel_refused(self):
        identity = self.submit()
        self.peer.state = "running"
        with self.assertRaises(ComfyError):
            self.client.cancel(identity)
        self.assertFalse(any(method == "POST" and path != "/prompt" for method, path, _ in self.peer.calls))

    def test_collect_and_no_overwrite(self):
        identity = self.submit()
        self.peer.state = "succeeded"
        assets = self.client.collect_assets(identity, self.root / "images")
        self.assertEqual(len(assets), 1)
        receipt = json.loads((self.root / "images/generation.json").read_text())
        self.assertEqual(receipt["outputs"][0]["node"], "9")
        self.assertEqual(receipt["outputs"][0]["sha256"], assets[0].sha256)
        with self.assertRaises(FileExistsError):
            self.client.collect_assets(identity, self.root / "images")

    def test_collect_requires_success(self):
        identity = self.submit()
        for state in ("queued", "running", "failed", "cancelled", "unknown"):
            self.peer.state = state
            with self.assertRaises(ComfyError):
                self.client.collect_assets(identity, self.root / "images")
        self.assertFalse((self.root / "images").exists())

    def test_windows_comfy_subfolder_is_collected_without_weakening_boundaries(self):
        identity = self.submit()
        self.peer.state = "succeeded"
        self.peer.output["subfolder"] = "workshop\\arch"
        self.client.collect_assets(identity, self.root / "images")
        self.assertTrue(any("subfolder=workshop%2Farch" in path for _, path, _ in self.peer.calls))
        for subfolder in ("..\\outside", "workshop\\..\\outside", "C:\\outside", "\\\\server\\share", ["bad"]):
            with self.subTest(subfolder=subfolder):
                self.peer.output["subfolder"] = subfolder
                before = len(self.peer.calls)
                with self.assertRaises(ValueError):
                    self.client.collect_assets(identity, self.root / "rejected")
                self.assertFalse((self.root / "rejected").exists())
                self.assertFalse(any(path.startswith('/view?') for _, path, _ in self.peer.calls[before:]))

    def test_output_path_and_type_rejected(self):
        identity = self.submit()
        self.peer.state = "succeeded"
        for item in ({"filename": "../bad.png", "type": "output"},
                     {"filename": "a.png", "subfolder": "../outside", "type": "output"},
                     {"filename": "a.png", "type": "input"}, {"filename": "a.mp4", "type": "output"}):
            self.peer.output = item
            with self.assertRaises(ValueError):
                self.client.collect_assets(identity, self.root / "images")

    def test_corrupt_image_rejected_before_destination(self):
        identity = self.submit()
        self.peer.state, self.peer.image = "succeeded", b"broken png"
        with self.assertRaises(ValueError):
            self.client.collect_assets(identity, self.root / "images")
        self.assertFalse((self.root / "images").exists())

    def test_ambiguous_submit_preserves_receipt_without_retry(self):
        self.peer.fail_submit = True
        with self.assertRaises(ComfyError):
            self.submit()
        self.assertEqual(self.client._job(self.peer.identity)["submission"], "uncertain")
        self.assertEqual(len(self.peer.calls), 1)

    def test_loopback_only_and_no_url_credentials(self):
        for endpoint in ("https://example.com", "http://localhost:8188", "http://127.0.0.1", "http://127.0.0.1:8188/a",
                         "http://user:pass@127.0.0.1:8188", "http://127.0.0.1:8188?secret=x"):
            with self.assertRaises(ValueError):
                LocalHTTP(endpoint)

    def test_invalid_seed_and_budget(self):
        for seed, budget in ((True, 60), (-1, 60), (2**64, 60), (2, float("nan")), (2, 0)):
            with self.assertRaises(ComfyError):
                self.client.submit_workflow(self.workflow, seed=seed, timeout_seconds=budget)
        self.assertFalse(self.peer.calls)

    def test_real_transport_builds_json_and_bounds_response(self):
        http = LocalHTTP(self.config["endpoint"])
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b"{}"
        http.opener = Mock()
        http.opener.open.return_value = response
        self.assertEqual(http("POST", "/prompt", {"prompt_id": "test"}, limit=20, timeout=3), b"{}")
        request = http.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8188/prompt")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"prompt_id": "test"})
        response.read.assert_called_once_with(21)
        response.read.return_value = b"x" * 21
        with self.assertRaises(ComfyError):
            http("GET", "/queue", limit=20)

    def test_transport_errors_are_sanitized(self):
        http = LocalHTTP(self.config["endpoint"])
        http.opener = Mock()
        http.opener.open.side_effect = OSError("sensitive local value")
        with self.assertRaises(ComfyError) as caught:
            http("GET", "/queue")
        self.assertNotIn("sensitive", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
