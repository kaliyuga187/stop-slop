"""X (Twitter) PFP fetcher.

Uses X API v2 `users/by/username`. Requires X_BEARER_TOKEN in env.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

log = logging.getLogger(__name__)

API_BASE = "https://api.twitter.com/2"


@dataclass
class XUser:
    id: str
    username: str
    profile_image_url: Optional[str]


class TwitterError(Exception):
    pass


def _upgrade_pfp_size(url: str) -> str:
    # X profile image URLs end with _normal.jpg / _bigger.jpg / _200x200.jpg.
    # Swap to _400x400 for a higher-fidelity hash.
    for suffix in ("_normal", "_bigger", "_mini", "_200x200"):
        if suffix in url:
            return url.replace(suffix, "_400x400")
    return url


def get_user(handle: str, bearer: Optional[str] = None, timeout: int = 15) -> XUser:
    bearer = bearer or os.environ.get("X_BEARER_TOKEN")
    if not bearer:
        raise TwitterError("X_BEARER_TOKEN is not set")

    handle = handle.lstrip("@").strip()
    url = f"{API_BASE}/users/by/username/{handle}"
    params = {"user.fields": "profile_image_url"}
    headers = {"Authorization": f"Bearer {bearer}"}

    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    if r.status_code == 429:
        raise TwitterError(f"rate-limited fetching @{handle}; retry after {r.headers.get('x-rate-limit-reset')}")
    if r.status_code != 200:
        raise TwitterError(f"X API {r.status_code} for @{handle}: {r.text[:200]}")

    payload = r.json().get("data")
    if not payload:
        raise TwitterError(f"X user @{handle} not found")

    pfp = payload.get("profile_image_url")
    if pfp:
        pfp = _upgrade_pfp_size(pfp)

    return XUser(id=payload["id"], username=payload["username"], profile_image_url=pfp)


def download_image(url: str, timeout: int = 20) -> bytes:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content
