# SPDX-License-Identifier: GPL-3.0-or-later
"""Small bounded RGB/RGBA raster codec, using Material Doctor's strict PNG envelope."""
import struct
import zlib
from .materials import png_info

MAX_PIXELS = 1024 * 1024


def decode(data):
    size = png_info(data)
    width, height = size["width"], size["height"]
    if width * height > MAX_PIXELS:
        raise ValueError("Layer raster exceeds one megapixel")
    channels = 3 if data[25] == 2 else 4
    compressed = bytearray()
    offset = 8
    while offset < len(data):
        count = struct.unpack_from(">I", data, offset)[0]
        if data[offset + 4:offset + 8] == b"IDAT":
            compressed.extend(data[offset + 8:offset + 8 + count])
        offset += count + 12
    raw = zlib.decompress(compressed)  # png_info already bounded the decompressed raster.
    stride = width * channels
    previous = bytearray(stride)
    rgba = bytearray(width * height * 4)
    for y in range(height):
        start = y * (stride + 1)
        mode = raw[start]
        row = bytearray(raw[start + 1:start + stride + 1])
        for i in range(stride):
            a = row[i - channels] if i >= channels else 0
            b = previous[i]
            c = previous[i - channels] if i >= channels else 0
            if mode == 1: predictor = a
            elif mode == 2: predictor = b
            elif mode == 3: predictor = (a + b) // 2
            elif mode == 4:
                p = a + b - c
                pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                predictor = a if pa <= pb and pa <= pc else b if pb <= pc else c
            else: predictor = 0
            row[i] = (row[i] + predictor) & 255
        for x in range(width):
            src, dst = x * channels, (y * width + x) * 4
            rgba[dst:dst+3] = row[src:src+3]
            rgba[dst+3] = row[src+3] if channels == 4 else 255
        previous = row
    return size, rgba


def encode(width, height, rgb):
    if (type(width) is not int or type(height) is not int or not 1 <= width <= 4096 or not 1 <= height <= 4096 or
            width * height > MAX_PIXELS or len(rgb) != width * height * 3):
        raise ValueError("Invalid RGB raster dimensions")
    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag+payload))
    raw = b"".join(b"\0" + rgb[y*width*3:(y+1)*width*3] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
