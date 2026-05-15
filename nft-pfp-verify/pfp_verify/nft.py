"""NFT lookup adapters.

EVM chains (Ethereum, Polygon, Optimism, Arbitrum, Base) use Alchemy's
`getNFTsForOwner` v3 endpoint. Solana uses Helius DAS `getAssetsByOwner`.

To add another chain, implement `fetch_nfts(wallet, max_n) -> list[Nft]` and
register it in CHAIN_FETCHERS.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional

import requests

log = logging.getLogger(__name__)

ALCHEMY_NETWORKS = {
    "eth": "eth-mainnet",
    "polygon": "polygon-mainnet",
    "optimism": "opt-mainnet",
    "arbitrum": "arb-mainnet",
    "base": "base-mainnet",
}

IPFS_GATEWAY = "https://ipfs.io/ipfs/"
ARWEAVE_GATEWAY = "https://arweave.net/"


@dataclass
class Nft:
    chain: str
    contract: str       # contract address (EVM) or mint (Solana)
    token_id: str       # token id (EVM) or "" for Solana
    image_url: Optional[str]
    name: Optional[str] = None


class NftError(Exception):
    pass


def normalize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if url.startswith("ipfs://"):
        path = url[len("ipfs://"):]
        if path.startswith("ipfs/"):
            path = path[len("ipfs/"):]
        return IPFS_GATEWAY + path
    if url.startswith("ar://"):
        return ARWEAVE_GATEWAY + url[len("ar://"):]
    return url


def fetch_evm_nfts(wallet: str, chain: str, max_n: int = 500) -> list[Nft]:
    api_key = os.environ.get("ALCHEMY_API_KEY")
    if not api_key:
        raise NftError("ALCHEMY_API_KEY is not set")
    network = ALCHEMY_NETWORKS.get(chain)
    if not network:
        raise NftError(f"unsupported EVM chain: {chain}")

    base = f"https://{network}.g.alchemy.com/nft/v3/{api_key}/getNFTsForOwner"
    out: list[Nft] = []
    page_key: Optional[str] = None

    while len(out) < max_n:
        params = {
            "owner": wallet,
            "withMetadata": "true",
            "pageSize": min(100, max_n - len(out)),
        }
        if page_key:
            params["pageKey"] = page_key

        r = requests.get(base, params=params, timeout=30)
        if r.status_code != 200:
            raise NftError(f"alchemy {chain} {r.status_code}: {r.text[:200]}")
        body = r.json()

        for item in body.get("ownedNfts", []):
            contract = (item.get("contract") or {}).get("address", "")
            token_id = item.get("tokenId", "")
            image = (item.get("image") or {}).get("cachedUrl") or (item.get("image") or {}).get("originalUrl")
            out.append(Nft(
                chain=chain,
                contract=contract,
                token_id=token_id,
                image_url=normalize_url(image),
                name=item.get("name"),
            ))
            if len(out) >= max_n:
                break

        page_key = body.get("pageKey")
        if not page_key:
            break

    return out


def fetch_solana_nfts(wallet: str, chain: str = "sol", max_n: int = 500) -> list[Nft]:
    api_key = os.environ.get("HELIUS_API_KEY")
    if not api_key:
        raise NftError("HELIUS_API_KEY is not set")

    url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    out: list[Nft] = []
    page = 1

    while len(out) < max_n:
        payload = {
            "jsonrpc": "2.0",
            "id": "pfp-verify",
            "method": "getAssetsByOwner",
            "params": {
                "ownerAddress": wallet,
                "page": page,
                "limit": min(1000, max_n - len(out)),
                "displayOptions": {"showFungible": False, "showNativeBalance": False},
            },
        }
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            raise NftError(f"helius {r.status_code}: {r.text[:200]}")
        body = r.json().get("result") or {}
        items = body.get("items") or []
        if not items:
            break

        for item in items:
            content = item.get("content") or {}
            files = content.get("files") or []
            image = None
            for f in files:
                if (f.get("mime") or "").startswith("image"):
                    image = f.get("uri") or f.get("cdn_uri")
                    break
            if not image:
                image = (content.get("links") or {}).get("image")

            metadata = content.get("metadata") or {}
            out.append(Nft(
                chain="sol",
                contract=item.get("id", ""),
                token_id="",
                image_url=normalize_url(image),
                name=metadata.get("name"),
            ))
            if len(out) >= max_n:
                break

        if len(items) < payload["params"]["limit"]:
            break
        page += 1

    return out


CHAIN_FETCHERS: dict[str, Callable[..., list[Nft]]] = {
    "eth": lambda w, n: fetch_evm_nfts(w, "eth", n),
    "polygon": lambda w, n: fetch_evm_nfts(w, "polygon", n),
    "optimism": lambda w, n: fetch_evm_nfts(w, "optimism", n),
    "arbitrum": lambda w, n: fetch_evm_nfts(w, "arbitrum", n),
    "base": lambda w, n: fetch_evm_nfts(w, "base", n),
    "sol": lambda w, n: fetch_solana_nfts(w, "sol", n),
}


def fetch_nfts(wallet: str, chain: str, max_n: int = 500) -> list[Nft]:
    fetcher = CHAIN_FETCHERS.get(chain)
    if not fetcher:
        raise NftError(f"unsupported chain: {chain} (supported: {sorted(CHAIN_FETCHERS)})")
    return fetcher(wallet, max_n)
