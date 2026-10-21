# SPDX-License-Identifier: GPL-3.0-or-later
"""Seeded periodic stylized textures, explicitly authored maps rather than AI inference."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import zlib

from .materials import load_material, pack_material
from .schema import integer
from .storage import write_json
from .world_assembly import palette


def _png(size, pixels):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    raster = b"".join(b"\0" + pixels[y*size*3:(y+1)*size*3] for y in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raster, 9)) + chunk(b"IEND", b""))


def sample_pattern(u, v, seed):
    """A continuous periodic field and analytic UV derivatives, period one in both axes."""
    phase = int.from_bytes(hashlib.sha256(str(seed).encode("ascii")).digest()[:4], "big") / 2**32 * 2*math.pi
    a, b = 2*math.pi*(2*u+v)+phase, 2*math.pi*(u-3*v)-phase
    height = .5 + .25*math.sin(a) + .25*math.cos(b)
    du = math.pi*math.cos(a) - .5*math.pi*math.sin(b)
    dv = .5*math.pi*math.cos(a) + 1.5*math.pi*math.sin(b)
    return height, du, dv


def generate_material(biome, destination, *, seed=42, size=128):
    biome = palette(biome)
    integer(seed, "seed", 0, 2**32-1)
    integer(size, "size", 32, 512)
    if size & (size - 1):
        raise ValueError("Use a power-of-two texture size")
    channels = {k: bytearray() for k in ("base_color", "roughness", "normal")}

    def byte(value):
        return max(0, min(255, round(value*255)))

    def srgb(value):
        return 12.92*value if value <= .0031308 else 1.055*value**(1/2.4)-.055

    for y in range(size):
        for x in range(size):
            h, du, dv = sample_pattern((x+.5)/size, (y+.5)/size, seed)
            channels["base_color"].extend(byte(srgb(c*(.65+.35*h))) for c in biome["color_linear"])
            rough = byte(min(1, max(.05, biome["roughness"] + .12*(h-.5))))
            channels["roughness"].extend((rough, rough, rough))
            # PNG row index runs downward; tangent +V runs upward. OpenGL +Y normals.
            nx, ny, nz = -.025*du, .025*dv, 1.0
            norm = math.sqrt(nx*nx + ny*ny + nz*nz)
            channels["normal"].extend(byte(.5+.5*c/norm) for c in (nx, ny, nz))
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Choose a new material destination")
    with tempfile.TemporaryDirectory(prefix=".biome-", dir=destination.parent) as temp:
        source = Path(temp)
        for role, pixels in channels.items():
            (source / (role + ".png")).write_bytes(_png(size, pixels))
        result = pack_material(source, {k: k + ".png" for k in channels}, destination)
    write_json(destination / "generator.json", {"schema": "cryptonyan.biome-material/1", "algorithm": "periodic-waves/1",
               "seed": seed, "size": size, "palette": biome, "physical_measurement": False,
               "material": result})
    return load_material(destination / "material.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate periodic base-colour, roughness and OpenGL normal maps")
    parser.add_argument("palette", type=Path)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--size", type=int, default=128)
    args = parser.parse_args(argv)
    from .runner_kit import read_json
    print(json.dumps(generate_material(read_json(args.palette), args.destination, seed=args.seed, size=args.size), indent=2))


if __name__ == "__main__":
    main()
