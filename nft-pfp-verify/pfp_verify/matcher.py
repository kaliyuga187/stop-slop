"""Perceptual hash matching.

`imagehash.phash` produces a 64-bit hash; Hamming distance ~0 means visually
identical, ~8 catches resizes and compression, >16 is usually a different image.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Optional

import imagehash
import requests
from PIL import Image, UnidentifiedImageError

log = logging.getLogger(__name__)


@dataclass
class MatchResult:
    matched: bool
    distance: Optional[int]
    nft_index: Optional[int]


class MatcherError(Exception):
    pass


def _open_image_from_bytes(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    # Convert to RGB so animated / palette / RGBA images hash consistently.
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def hash_bytes(data: bytes) -> imagehash.ImageHash:
    return imagehash.phash(_open_image_from_bytes(data))


def hash_url(url: str, timeout: int = 20) -> Optional[imagehash.ImageHash]:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return hash_bytes(r.content)
    except (requests.RequestException, UnidentifiedImageError, OSError) as e:
        log.warning("failed to hash %s: %s", url, e)
        return None


def best_match(pfp_hash: imagehash.ImageHash, nft_hashes: list[Optional[imagehash.ImageHash]], threshold: int) -> MatchResult:
    """Return the closest NFT to the PFP. `matched` is True iff distance <= threshold."""
    best_idx: Optional[int] = None
    best_dist: Optional[int] = None
    for i, h in enumerate(nft_hashes):
        if h is None:
            continue
        d = pfp_hash - h
        if best_dist is None or d < best_dist:
            best_dist = d
            best_idx = i
    if best_idx is None:
        return MatchResult(matched=False, distance=None, nft_index=None)
    return MatchResult(matched=best_dist <= threshold, distance=best_dist, nft_index=best_idx)
