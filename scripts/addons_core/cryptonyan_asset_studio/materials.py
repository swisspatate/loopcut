# SPDX-License-Identifier: GPL-3.0-or-later
"""Material Doctor: bounded PNG validation and explicit PBR channel bundles.

No AI inference: a colour image is never silently labelled roughness or normal.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from .storage import digest, safe_path, write_json

MAX_IMAGE_BYTES = 32 * 1024 * 1024
CHANNELS = {"base_color": "sRGB", "roughness": "Non-Color", "metallic": "Non-Color", "normal": "Non-Color"}


def png_info(data):
    """Accept complete noninterlaced 8-bit RGB/RGBA PNGs up to 4096 square.

    Validate CRCs, decompressed size and row filters before passing to a decoder.
    Pixel content/physical correctness is intentionally not assessed.
    """
    if len(data) > MAX_IMAGE_BYTES or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Expected a bounded PNG")
    offset, chunks, compressed, ended = 8, [], bytearray(), False
    while offset + 12 <= len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        tag = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        end = offset + 12 + size
        if end > len(data) or zlib.crc32(tag + payload) != struct.unpack_from(">I", data, end - 4)[0]:
            raise ValueError("PNG chunk integrity failed")
        if tag == b"IHDR":
            if chunks or size != 13:
                raise ValueError("Invalid PNG header")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if not (1 <= width <= 4096 and 1 <= height <= 4096) or depth != 8 or color not in (2, 6) or any((compression, filtering, interlace)):
                raise ValueError("Require noninterlaced RGB/RGBA 8-bit PNG, maximum 4096x4096")
        elif not chunks:
            raise ValueError("Missing PNG header")
        elif tag == b"IDAT":
            if b"IDAT" in chunks and chunks[-1] != b"IDAT":
                raise ValueError("Noncontiguous PNG data")
            compressed.extend(payload)
        elif tag == b"IEND":
            if size or b"IDAT" not in chunks or end != len(data):
                raise ValueError("Invalid PNG end")
            ended = True
        elif tag in (b"acTL", b"fcTL", b"fdAT") or not tag[0] & 32:
            raise ValueError("Animated or unsupported critical PNG chunk")
        chunks.append(tag)
        offset = end
        if ended:
            break
    if not ended:
        raise ValueError("Truncated PNG")
    stride = width * (3 if color == 2 else 4) + 1
    expected = height * stride
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(compressed, expected + 1)
    except zlib.error:
        raise ValueError("Invalid PNG compression") from None
    if len(raw) != expected or not decoder.eof or decoder.unused_data or any(raw[i] > 4 for i in range(0, len(raw), stride)):
        raise ValueError("Invalid PNG raster size or filters")
    return {"width": width, "height": height}


def read_png(path):
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("Texture exceeds byte budget")
    data = path.read_bytes()
    return data, png_info(data)


def load_material(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError("Invalid material manifest")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if set(data) != {"schema", "normal_convention", "channels"} or data["schema"] != "cryptonyan.material/1" or data["normal_convention"] != "OpenGL":
        raise ValueError("Unsupported material contract; normals must use OpenGL +Y")
    channels = data["channels"]
    if not isinstance(channels, dict) or "base_color" not in channels or not set(channels) <= CHANNELS.keys():
        raise ValueError("Require base_color and supported channels")
    sizes = set()
    for role, item in channels.items():
        if set(item) != {"file", "sha256", "color_space", "width", "height"} or item["file"] != role + ".png" or item["color_space"] != CHANNELS[role]:
            raise ValueError("Invalid channel path or colour space")
        image = safe_path(path.parent, item["file"])
        _, size = read_png(image)
        if digest(image) != item["sha256"] or size != {k: item[k] for k in ("width", "height")}:
            raise ValueError("Material texture integrity failed")
        sizes.add((size["width"], size["height"]))
    if len(sizes) != 1:
        raise ValueError("PBR channels must share dimensions")
    return data


def pack_material(source, channels, destination):
    """Copy explicit channel assignments into a new, validated portable directory."""
    if not isinstance(channels, dict) or "base_color" not in channels or not set(channels) <= CHANNELS.keys():
        raise ValueError("Invalid channel assignments")
    prepared = {}
    for role, relative in channels.items():
        prepared[role] = read_png(safe_path(source, relative))
    if len({(size["width"], size["height"]) for _, size in prepared.values()}) != 1:
        raise ValueError("PBR channels must share dimensions")
    destination = Path(destination)
    destination.mkdir(parents=False, exist_ok=False)
    result = {"schema": "cryptonyan.material/1", "normal_convention": "OpenGL", "channels": {}}
    for role, (payload, size) in prepared.items():
        (destination / (role + ".png")).write_bytes(payload)
        result["channels"][role] = {"file": role + ".png", "sha256": hashlib.sha256(payload).hexdigest(),
                                    "color_space": CHANNELS[role], **size}
    write_json(destination / "material.json", result)
    return load_material(destination / "material.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Material Doctor: validate or pack explicit PBR PNG channels")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("manifest", type=Path)
    pack = commands.add_parser("pack")
    pack.add_argument("--source", required=True, type=Path)
    pack.add_argument("--channels", required=True, type=Path, help="JSON mapping roles to source-relative PNG filenames")
    pack.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    result = load_material(args.manifest) if args.command == "check" else pack_material(
        args.source, json.loads(args.channels.read_text(encoding="utf-8-sig")), args.destination)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
