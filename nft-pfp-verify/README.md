# nft-pfp-verify

A CLI tool for verifying whether a community member's X (Twitter) profile picture is an NFT they actually own.

Given a list of `(wallet, chain, x_handle)` rows, it fetches each handle's current PFP, fetches the wallet's NFTs from on-chain indexers, and compares images with a perceptual hash to flag matches. Optional best-effort historical PFP lookup via the Wayback Machine.

## What "verified" means here

A row is marked `verified=true` when **both** of these are true:

1. The wallet currently holds an NFT in some collection.
2. The X account's profile picture is perceptually the same image as one of those NFTs (Hamming distance on a 64-bit pHash below a threshold, default `8`).

If only one side matches, the row is reported but not verified.

## Hard limits (read this before opening issues)

- **Wallet ↔ X handle mapping is your problem.** There is no canonical source. Feed it a CSV. Communities typically generate this from Collab.Land, Premint, Discord-linked-wallet exports, or hand-compiled lists.
- **"All chains" really means: EVM (Ethereum, Polygon, Optimism, Arbitrum, Base) via Alchemy, and Solana via Helius.** Other chains need a new adapter in `pfp_verify/nft.py`. The adapter interface is ~20 lines.
- **Historical PFPs are best-effort.** X's API does not expose PFP history. The `--include-history` flag queries the Wayback Machine CDX index for snapshots of `twitter.com/<handle>` and extracts `profile_image_url` references from the HTML. Many accounts have zero snapshots; many snapshots have stale URLs that 404. Treat it as a hint, not ground truth.
- **Perceptual matching is fuzzy.** A pHash threshold of 8 catches resizes, JPEG compression, minor crops, and small color edits. It can miss heavy edits (added accessories, recolors) and can occasionally false-positive on visually similar collection art. Tune `--threshold` per collection.

## Install

```bash
cd nft-pfp-verify
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in API keys
```

You need:

- `X_BEARER_TOKEN` — X API v2 bearer (any tier with `users/by/username` access)
- `ALCHEMY_API_KEY` — for EVM NFT data
- `HELIUS_API_KEY` — for Solana NFT data

If a key is missing, the corresponding chain is skipped (with a warning) rather than crashing.

## Use

```bash
python -m pfp_verify.cli check \
  --input samples/holders.csv \
  --output results.csv
```

Input CSV columns: `wallet,chain,x_handle`. Supported `chain` values: `eth`, `polygon`, `optimism`, `arbitrum`, `base`, `sol`.

Output CSV columns: `wallet,chain,x_handle,pfp_url,verified,match_contract,match_token_id,match_image_url,similarity_distance,notes`.

Flags:

- `--threshold N` — Hamming-distance cutoff (default `8`, lower = stricter)
- `--include-history` — also query Wayback for past PFPs
- `--max-nfts N` — cap per-wallet NFT count to keep API costs bounded (default `500`)
- `--verbose` — log each row

## How it works

1. **PFP fetch** (`twitter.py`) — `GET /2/users/by/username/{handle}?user.fields=profile_image_url`, then upgrades the URL to `_400x400` for better hashing.
2. **NFT fetch** (`nft.py`) — chain-specific adapter. EVM uses Alchemy's `getNFTsForOwner`; Solana uses Helius DAS `getAssetsByOwner`. Image URLs are normalized (`ipfs://` → `https://ipfs.io/ipfs/`, `ar://` → `https://arweave.net/`).
3. **Match** (`matcher.py`) — both images are decoded with Pillow, downscaled, and pHashed (`imagehash.phash`, 8x8 default). Hamming distance below threshold = match.
4. **History** (`wayback.py`, optional) — Wayback CDX query for snapshots of the handle's profile page, regex-scan for `profile_images/...jpg` URLs, dedupe.

## Limitations of the indicator itself

A `verified` flag tells you the PFP-NFT relationship holds *right now*. It doesn't tell you:

- Whether the wallet ever held the NFT in the past (would need historical balance data)
- Whether the X account has been continuously the same person
- Whether the NFT was bought specifically to match the PFP (or vice versa)

Treat the output as a snapshot, not a provenance record.
