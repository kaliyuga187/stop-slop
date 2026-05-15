"""Best-effort historical PFP retrieval via the Wayback Machine.

X doesn't expose PFP history. This module queries the CDX index for snapshots
of `twitter.com/<handle>` and `x.com/<handle>`, scrapes `profile_images/...`
URLs from the HTML, and dedupes. Many accounts return zero useful snapshots.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

import requests

log = logging.getLogger(__name__)

CDX_API = "https://web.archive.org/cdx/search/cdx"
SNAPSHOT_BASE = "https://web.archive.org/web"

# Matches X profile-image asset URLs (current + legacy hosts).
PFP_RE = re.compile(
    r"https?://(?:pbs\.twimg\.com/profile_images|si0\.twimg\.com/profile_images)/[^\"'>\s]+"
)


def _cdx_snapshots(handle: str, limit: int = 25) -> list[str]:
    handle = handle.lstrip("@")
    out: list[str] = []
    for host in ("twitter.com", "x.com"):
        try:
            r = requests.get(
                CDX_API,
                params={
                    "url": f"{host}/{handle}",
                    "output": "json",
                    "limit": str(limit),
                    "filter": "statuscode:200",
                    "collapse": "timestamp:6",
                },
                timeout=20,
            )
            if r.status_code != 200:
                continue
            rows = r.json()
            if not rows or len(rows) < 2:
                continue
            for row in rows[1:]:
                # CDX columns: urlkey, timestamp, original, mimetype, statuscode, digest, length
                timestamp, original = row[1], row[2]
                out.append(f"{SNAPSHOT_BASE}/{timestamp}id_/{original}")
        except requests.RequestException as e:
            log.warning("CDX query failed for %s/%s: %s", host, handle, e)
    return out


def historical_pfp_urls(handle: str, max_snapshots: int = 25) -> list[str]:
    snapshots = _cdx_snapshots(handle, max_snapshots)
    found: set[str] = set()
    for snap_url in snapshots:
        try:
            r = requests.get(snap_url, timeout=20)
            if r.status_code != 200:
                continue
            for url in PFP_RE.findall(r.text):
                # Upgrade to _400x400 for hashable resolution
                for suffix in ("_normal", "_bigger", "_mini", "_200x200"):
                    if suffix in url:
                        url = url.replace(suffix, "_400x400")
                        break
                found.add(url)
        except requests.RequestException as e:
            log.warning("wayback fetch failed %s: %s", snap_url, e)
    return sorted(found)
