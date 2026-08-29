"""Canonical image hashing used by provenance manifests."""

from __future__ import annotations

import hashlib
import struct
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from PIL import Image


CANONICAL_HASH_ALGORITHM = "sha256(big_endian_uint32(width) || big_endian_uint32(height) || RGB_pixel_bytes_row_major)"


def decoded_rgb_sha256(image: Image.Image) -> str:
    """Hash dimensions and decoded RGB pixels using a stable procedure."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    payload = struct.pack(">II", width, height) + rgb.tobytes()
    return hashlib.sha256(payload).hexdigest()


def decoded_rgb_sha256_path(path: Path) -> tuple[str, int, int]:
    with Image.open(path) as image:
        width, height = image.size
        return decoded_rgb_sha256(image), width, height


def decode_source(image_record: object) -> tuple[Image.Image, bytes | None, str]:
    """Decode a datasets image record while retaining bytes/path provenance."""
    if isinstance(image_record, Image.Image):
        return image_record, None, ""
    if not isinstance(image_record, dict):
        raise TypeError(f"Unsupported image record type: {type(image_record)!r}")
    raw = image_record.get("bytes")
    source_path = str(image_record.get("path") or "")
    if raw is not None:
        image = Image.open(BytesIO(raw))
        image.load()
        return image, raw, source_path
    if source_path:
        path = Path(source_path)
        raw = path.read_bytes() if path.is_file() else None
        image = Image.open(path)
        image.load()
        return image, raw, source_path
    raise ValueError("Image record contains neither bytes nor path")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

