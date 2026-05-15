"""Smoke tests for matcher and nft URL normalization. Run: python -m unittest discover."""

from __future__ import annotations

import io
import unittest

from PIL import Image

from pfp_verify import matcher, nft


def _png_bytes_pattern(seed: int) -> bytes:
    # pHash is based on DCT of luminance, so we need actual spatial structure.
    img = Image.new("RGB", (64, 64))
    px = img.load()
    for y in range(64):
        for x in range(64):
            v = ((x * 7 + y * 13 + seed * 29) // 4) % 256
            px[x, y] = (v, (v * 3) % 256, (v * 5) % 256)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class MatcherTests(unittest.TestCase):
    def test_identical_images_match(self):
        h1 = matcher.hash_bytes(_png_bytes_pattern(1))
        h2 = matcher.hash_bytes(_png_bytes_pattern(1))
        self.assertEqual(h1 - h2, 0)

    def test_best_match_picks_closest(self):
        target = matcher.hash_bytes(_png_bytes_pattern(2))
        candidates = [
            matcher.hash_bytes(_png_bytes_pattern(9)),
            matcher.hash_bytes(_png_bytes_pattern(2)),  # exact match
            matcher.hash_bytes(_png_bytes_pattern(17)),
        ]
        result = matcher.best_match(target, candidates, threshold=4)
        self.assertEqual(result.nft_index, 1)
        self.assertTrue(result.matched)

    def test_no_candidates_returns_empty(self):
        target = matcher.hash_bytes(_png_bytes_pattern(3))
        result = matcher.best_match(target, [None, None], threshold=8)
        self.assertFalse(result.matched)
        self.assertIsNone(result.nft_index)


class UrlNormalizationTests(unittest.TestCase):
    def test_ipfs_scheme(self):
        self.assertEqual(
            nft.normalize_url("ipfs://QmHash/img.png"),
            "https://ipfs.io/ipfs/QmHash/img.png",
        )

    def test_ipfs_with_prefix(self):
        self.assertEqual(
            nft.normalize_url("ipfs://ipfs/QmHash/img.png"),
            "https://ipfs.io/ipfs/QmHash/img.png",
        )

    def test_arweave_scheme(self):
        self.assertEqual(
            nft.normalize_url("ar://abc123"),
            "https://arweave.net/abc123",
        )

    def test_passthrough(self):
        self.assertEqual(
            nft.normalize_url("https://example.com/x.png"),
            "https://example.com/x.png",
        )

    def test_none(self):
        self.assertIsNone(nft.normalize_url(None))


if __name__ == "__main__":
    unittest.main()
