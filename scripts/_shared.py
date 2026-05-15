"""Shared helpers for the slop linter and rule miner.

Loads the skill bundle once and exposes a thin wrapper that calls Claude with
the bundle attached as a cached system block. Everything that talks to the
Anthropic API goes through here.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = REPO_ROOT / "SKILL.md"
REFERENCES_DIR = REPO_ROOT / "references"

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4096"))
RETRY_ATTEMPTS = int(os.environ.get("ANTHROPIC_RETRY_ATTEMPTS", "4"))
RETRY_BASE_SECONDS = float(os.environ.get("ANTHROPIC_RETRY_BASE_SECONDS", "2.0"))


@dataclass
class SkillBundle:
    skill_md: str
    phrases_md: str
    structures_md: str
    examples_md: str

    def as_system_text(self) -> str:
        return (
            "You are applying the Stop Slop skill. The skill definition and "
            "its reference files follow. Apply them faithfully.\n\n"
            "===== SKILL.md =====\n"
            f"{self.skill_md}\n\n"
            "===== references/phrases.md =====\n"
            f"{self.phrases_md}\n\n"
            "===== references/structures.md =====\n"
            f"{self.structures_md}\n\n"
            "===== references/examples.md =====\n"
            f"{self.examples_md}\n"
        )


def load_skill_bundle() -> SkillBundle:
    return SkillBundle(
        skill_md=SKILL_PATH.read_text(encoding="utf-8"),
        phrases_md=(REFERENCES_DIR / "phrases.md").read_text(encoding="utf-8"),
        structures_md=(REFERENCES_DIR / "structures.md").read_text(encoding="utf-8"),
        examples_md=(REFERENCES_DIR / "examples.md").read_text(encoding="utf-8"),
    )


def get_client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=key)


# Retry these on transient failures. Authentication / bad-request errors
# bubble up immediately so misconfiguration fails loudly.
_RETRYABLE = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
)


def call_claude(
    client: anthropic.Anthropic,
    bundle: SkillBundle,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    extra_system: str | None = None,
) -> str:
    """Send a single-turn request with the skill bundle cached as a system block.

    Retries transient errors (rate limits, network blips, 5xx, timeouts) with
    exponential backoff plus jitter. Permanent errors (auth, bad request)
    propagate on the first attempt.
    """

    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": bundle.as_system_text(),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if extra_system:
        system_blocks.append({"type": "text", "text": extra_system})

    last_error: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens or MAX_TOKENS,
                system=system_blocks,
                messages=[{"role": "user", "content": user_prompt}],
            )
            break
        except _RETRYABLE as e:
            last_error = e
            if attempt == RETRY_ATTEMPTS - 1:
                raise
            delay = RETRY_BASE_SECONDS * (2**attempt) + random.uniform(0, 0.5)
            print(
                f"Anthropic transient error ({type(e).__name__}); "
                f"retry {attempt + 1}/{RETRY_ATTEMPTS - 1} after {delay:.1f}s",
                file=sys.stderr,
            )
            time.sleep(delay)
    else:  # pragma: no cover - unreachable because we either break or raise
        raise RuntimeError(f"Exhausted retries calling Anthropic: {last_error}")

    parts: list[str] = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts).strip()


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Pull JSON out of Claude's reply.

    Handles fenced ```json blocks and bare JSON. Raises ValueError if nothing
    parseable is found, so callers can decide whether to retry or fail.
    """
    candidates: list[str] = []
    fenced = _JSON_FENCE.findall(text)
    candidates.extend(s.strip() for s in fenced)
    candidates.append(text.strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(candidate[start : end + 1])
                except json.JSONDecodeError:
                    pass
            start = candidate.find("[")
            end = candidate.rfind("]")
            if start != -1 and end > start:
                try:
                    return json.loads(candidate[start : end + 1])
                except json.JSONDecodeError:
                    pass

    raise ValueError(f"Could not parse JSON from model output:\n{text[:500]}")
