"""CLI orchestrator for NFT-PFP verification.

Usage:
    python -m pfp_verify.cli check --input holders.csv --output results.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

from . import matcher, nft, twitter, wayback

log = logging.getLogger("pfp_verify")

OUTPUT_FIELDS = [
    "wallet",
    "chain",
    "x_handle",
    "pfp_url",
    "verified",
    "match_contract",
    "match_token_id",
    "match_image_url",
    "similarity_distance",
    "history_verified",
    "notes",
]


@dataclass
class RowResult:
    wallet: str
    chain: str
    x_handle: str
    pfp_url: Optional[str] = None
    verified: bool = False
    match_contract: Optional[str] = None
    match_token_id: Optional[str] = None
    match_image_url: Optional[str] = None
    similarity_distance: Optional[int] = None
    history_verified: bool = False
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "wallet": self.wallet,
            "chain": self.chain,
            "x_handle": self.x_handle,
            "pfp_url": self.pfp_url or "",
            "verified": "true" if self.verified else "false",
            "match_contract": self.match_contract or "",
            "match_token_id": self.match_token_id or "",
            "match_image_url": self.match_image_url or "",
            "similarity_distance": "" if self.similarity_distance is None else str(self.similarity_distance),
            "history_verified": "true" if self.history_verified else "false",
            "notes": self.notes,
        }


def process_row(
    wallet: str,
    chain: str,
    handle: str,
    threshold: int,
    max_nfts: int,
    include_history: bool,
) -> RowResult:
    res = RowResult(wallet=wallet, chain=chain, x_handle=handle)
    notes: list[str] = []

    try:
        user = twitter.get_user(handle)
    except twitter.TwitterError as e:
        res.notes = f"twitter: {e}"
        return res

    res.pfp_url = user.profile_image_url
    if not res.pfp_url:
        res.notes = "no profile image on X"
        return res

    pfp_hash = matcher.hash_url(res.pfp_url)
    if pfp_hash is None:
        res.notes = "could not decode PFP image"
        return res

    try:
        nfts = nft.fetch_nfts(wallet, chain, max_nfts)
    except nft.NftError as e:
        res.notes = f"nft: {e}"
        return res

    if not nfts:
        res.notes = "wallet holds no NFTs on this chain"
        return res

    nft_hashes = [matcher.hash_url(n.image_url) if n.image_url else None for n in nfts]
    match = matcher.best_match(pfp_hash, nft_hashes, threshold)

    if match.nft_index is not None:
        hit = nfts[match.nft_index]
        res.match_contract = hit.contract
        res.match_token_id = hit.token_id
        res.match_image_url = hit.image_url
        res.similarity_distance = match.distance
        res.verified = match.matched
        if not match.matched:
            notes.append(f"closest distance {match.distance} above threshold {threshold}")

    if include_history:
        try:
            for url in wayback.historical_pfp_urls(handle):
                h = matcher.hash_url(url)
                if h is None:
                    continue
                hmatch = matcher.best_match(h, nft_hashes, threshold)
                if hmatch.matched:
                    res.history_verified = True
                    break
        except Exception as e:  # noqa: BLE001 — wayback is best-effort
            notes.append(f"wayback: {e}")

    res.notes = "; ".join(notes)
    return res


def cmd_check(args: argparse.Namespace) -> int:
    load_dotenv()

    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"wallet", "chain", "x_handle"}
        if not required.issubset(reader.fieldnames or []):
            print(f"input CSV must have columns: {sorted(required)}", file=sys.stderr)
            return 2
        rows = list(reader)

    results: list[RowResult] = []
    for i, row in enumerate(rows, start=1):
        wallet = row["wallet"].strip()
        chain = row["chain"].strip().lower()
        handle = row["x_handle"].strip().lstrip("@")
        if args.verbose:
            log.info("[%d/%d] %s (%s) @%s", i, len(rows), wallet, chain, handle)
        result = process_row(
            wallet=wallet,
            chain=chain,
            handle=handle,
            threshold=args.threshold,
            max_nfts=args.max_nfts,
            include_history=args.include_history,
        )
        results.append(result)

    out_stream = sys.stdout if args.output == "-" else open(args.output, "w", newline="", encoding="utf-8")
    try:
        writer = csv.DictWriter(out_stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for r in results:
            writer.writerow(r.as_dict())
    finally:
        if out_stream is not sys.stdout:
            out_stream.close()

    verified = sum(1 for r in results if r.verified)
    print(f"checked {len(results)} rows, {verified} verified", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pfp-verify", description="Verify whether X PFPs are NFTs the wallet holds.")
    sub = p.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="check a CSV of holders")
    check.add_argument("--input", "-i", required=True, help="input CSV: wallet,chain,x_handle")
    check.add_argument("--output", "-o", default="-", help="output CSV path or '-' for stdout (default '-')")
    check.add_argument("--threshold", "-t", type=int, default=8, help="pHash Hamming distance cutoff (default 8)")
    check.add_argument("--max-nfts", type=int, default=500, help="max NFTs to fetch per wallet (default 500)")
    check.add_argument("--include-history", action="store_true", help="also check historical PFPs via Wayback")
    check.add_argument("--verbose", "-v", action="store_true")
    check.set_defaults(func=cmd_check)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
