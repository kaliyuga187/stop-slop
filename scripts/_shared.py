"""Shared helpers for the slop linter and rule miner.

Loads the skill bundle once and exposes a thin wrapper that calls Claude with
the bundle attached as a cached system block. Everything that talks to the
Anthropic API goes through here.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = REPO_ROOT / "SKILL.md"
REFERENCES_DIR = REPO_ROOT / "references"

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4096"))


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


def call_claude(
    client: anthropic.Anthropic,
    bundle: SkillBundle,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    extra_system: str | None = None,
) -> str:
    """Send a single-turn request with the skill bundle cached as a system block."""

    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": bundle.as_system_text(),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if extra_system:
        system_blocks.append({"type": "text", "text": extra_system})

    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens or MAX_TOKENS,
        system=system_blocks,
        messages=[{"role": "user", "content": user_prompt}],
    )

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
