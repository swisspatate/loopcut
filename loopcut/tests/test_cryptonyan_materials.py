# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable material integrity checks; no Blender/image-library dependency."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/addons_core"))
from cryptonyan_asset_studio.materials import load_material, pack_material, png_info
from cryptonyan_asset_studio.publication import texture_inventory


def png(rgb=(128, 128, 255), width=2, height=2):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress((b"\x00" + bytes(rgb) * width) * height)) + chunk(b"IEND", b""))


class MaterialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "color.png").write_bytes(png())

    def pack(self, **channels):
        return pack_material(self.root, {"base_color": "color.png", **channels}, self.root / "bundle")

    def test_pack_check_and_no_overwrite(self):
        data = self.pack()
        self.assertEqual(data, load_material(self.root / "bundle/material.json"))
        self.assertEqual(data["channels"]["base_color"]["color_space"], "sRGB")
        with self.assertRaises(FileExistsError):
            self.pack()

    def test_png_crc_truncation_and_trailing_bytes(self):
        data = png()
        for bad in (data[:-1], data + b"extra", data[:35] + b"X" + data[36:], b"JPEG"):
            with self.subTest(bad=bad[:20]), self.assertRaises(ValueError):
                png_info(bad)

    def test_png_dimension_and_decompression_budget(self):
        with self.assertRaises(ValueError):
            png_info(png(width=4097, height=1))
        # Header says 1x1 while compressed raster contains 2x2; recompute header CRC.
        data = bytearray(png())
        data[16:24] = struct.pack(">II", 1, 1)
        data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]))
        with self.assertRaises(ValueError):
            png_info(bytes(data))

    def test_channels_are_explicit(self):
        for channels in ({"normal": "color.png"}, {"base_color": "color.png", "height": "color.png"}):
            with self.assertRaises(ValueError):
                pack_material(self.root, channels, self.root / "bundle")

    def test_path_escape_rejected(self):
        for path in ("../color.png", "/color.png", "C:/color.png", "a\\b.png"):
            with self.assertRaises(ValueError):
                pack_material(self.root, {"base_color": path}, self.root / "bundle")

    def test_mismatched_resolutions_rejected_before_output(self):
        (self.root / "normal.png").write_bytes(png(width=1))
        with self.assertRaises(ValueError):
            self.pack(normal="normal.png")
        self.assertFalse((self.root / "bundle").exists())

    def test_tampered_image(self):
        self.pack()
        (self.root / "bundle/base_color.png").write_bytes(png((1, 2, 3)))
        with self.assertRaises(ValueError):
            load_material(self.root / "bundle/material.json")

    def test_colorspace_and_normal_convention(self):
        original = self.pack(normal="color.png")
        for field in ("normal_convention", "color_space"):
            data = copy.deepcopy(original)
            if field == "normal_convention":
                data[field] = "DirectX"
            else:
                data["channels"]["normal"][field] = "sRGB"
            (self.root / "bundle/material.json").write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                load_material(self.root / "bundle/material.json")

    def test_symlink_texture_rejected(self):
        self.pack()
        path = self.root / "bundle/base_color.png"
        path.unlink()
        try:
            path.symlink_to(self.root / "color.png")
        except OSError:
            self.skipTest("OS does not permit test symlinks")
        with self.assertRaises(ValueError):
            load_material(self.root / "bundle/material.json")

    def test_embedded_gltf_inventory_and_external_rejection(self):
        binary = png()
        document = {"images": [{"bufferView": 0, "mimeType": "image/png"}], "textures": [{"source": 0}],
                    "bufferViews": [{"byteLength": len(binary), "buffer": 0}],
                    "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
                    "meshes": [{"primitives": [{"attributes": {"TEXCOORD_0": 0}}]}]}
        self.assertEqual(texture_inventory(document, binary)[0]["role"], "base_color")
        for change in ("uri", "uv", "extension", "unused"):
            bad = copy.deepcopy(document)
            if change == "uri":
                bad["images"][0]["uri"] = "file:///outside.png"
            elif change == "uv":
                bad["meshes"][0]["primitives"][0]["attributes"].clear()
            elif change == "extension":
                bad["textures"][0]["extensions"] = {"KHR_texture_basisu": {"source": 0}}
            else:
                bad["images"].append(bad["images"][0])
            with self.subTest(change=change), self.assertRaises(ValueError):
                texture_inventory(bad, binary)


if __name__ == "__main__":
    unittest.main()
