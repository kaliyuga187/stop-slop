"""Mine new slop-detection rules from a corpus of AI-generated prose.

Pipeline:
  1. Load samples from corpus/samples/*.{md,txt} and fetch URLs in corpus/sources.txt.
  2. For each sample, ask Claude what slop patterns appear that are NOT already
     covered by the current rule set.
  3. Aggregate candidates across samples, then ask Claude to dedupe/cluster and
     report frequency.
  4. For clusters at or above MIN_FREQUENCY, draft additions for either
     references/phrases.md or references/structures.md.
  5. Write the additions to the working tree and open a pull request.

Inputs (env):
    GITHUB_TOKEN              - PAT or GITHUB_TOKEN with `contents:write` and `pull-requests:write`
    GITHUB_REPOSITORY         - "owner/repo"
    ANTHROPIC_API_KEY         - Claude API key
    ANTHROPIC_MODEL           - optional, defaults to claude-sonnet-4-6
    MINE_RULES_MIN_FREQUENCY  - optional, defaults to 2
    MINE_RULES_MAX_SAMPLES    - optional, defaults to 25 (cap to control cost)
    MINE_RULES_DRY_RUN        - if "1", write files locally and skip PR creation
    MINE_RULES_BASE_BRANCH    - optional, defaults to "main"
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from _shared import (
    REFERENCES_DIR,
    REPO_ROOT,
    call_claude,
    extract_json,
    get_client,
    load_skill_bundle,
)

GITHUB_API = "https://api.github.com"
CORPUS_DIR = REPO_ROOT / "corpus"
SAMPLES_DIR = CORPUS_DIR / "samples"
SOURCES_FILE = CORPUS_DIR / "sources.txt"

MIN_FREQUENCY = int(os.environ.get("MINE_RULES_MIN_FREQUENCY", "2"))
MAX_SAMPLES = int(os.environ.get("MINE_RULES_MAX_SAMPLES", "25"))
BASE_BRANCH = os.environ.get("MINE_RULES_BASE_BRANCH", "main")
DRY_RUN = os.environ.get("MINE_RULES_DRY_RUN") == "1"


@dataclass
class Sample:
    name: str
    text: str


def load_local_samples() -> list[Sample]:
    out: list[Sample] = []
    if not SAMPLES_DIR.exists():
        return out
    for path in sorted(SAMPLES_DIR.iterdir()):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"WARN: could not read {path}: {e}", file=sys.stderr)
            continue
        if text.strip():
            out.append(Sample(name=f"samples/{path.name}", text=text))
    return out


def load_url_samples() -> list[Sample]:
    out: list[Sample] = []
    if not SOURCES_FILE.exists():
        return out
    urls = [
        line.strip()
        for line in SOURCES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "stop-slop-miner/1.0"})
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"WARN: could not fetch {url}: {e}", file=sys.stderr)
            continue
        text = r.text
        if not text.strip():
            continue
        # Truncate hard so a single huge page can't blow the token budget.
        if len(text) > 20000:
            text = text[:20000]
        out.append(Sample(name=url, text=text))
    return out


NOVELTY_PROMPT = """\
The Stop Slop skill catalogues AI writing tells (phrases and structural
patterns). Your job is to surface NEW slop patterns that appear in the sample
below but are NOT already covered by the skill's existing rules.

Sample source: {name}

Sample text:
<<<
{text}
>>>

Return ONLY a JSON object with this shape:

{{
  "candidates": [
    {{
      "kind": "phrase" | "structure",
      "pattern": "<short description of the pattern, e.g. 'Throat-clearing opener: I want to share...' or 'Three-part rhetorical staircase'>",
      "example_quote": "<verbatim quote from the sample showing the pattern, kept under 200 chars>",
      "why_slop": "<one sentence on why this is a tell>",
      "suggested_fix": "<one sentence on how to rewrite>"
    }}
  ]
}}

Rules:
- Skip anything already covered, even implicitly, by the existing rules.
- Be conservative. Only flag patterns a careful human editor would call slop.
- Cap at 8 candidates per sample. Pick the strongest.
- If the sample shows no novel slop, return {{"candidates": []}}.
- Do not include any prose outside the JSON object.
"""


def find_candidates_in_sample(client: Any, bundle: Any, sample: Sample) -> list[dict[str, Any]]:
    text = sample.text
    if len(text) > 12000:
        text = text[:12000]
    prompt = NOVELTY_PROMPT.format(name=sample.name, text=text)
    raw = call_claude(client, bundle, prompt, max_tokens=2048)
    try:
        data = extract_json(raw)
    except ValueError as e:
        print(f"WARN: novelty pass failed for {sample.name}: {e}", file=sys.stderr)
        return []
    candidates = data.get("candidates", []) if isinstance(data, dict) else []
    cleaned: list[dict[str, Any]] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        kind = c.get("kind")
        if kind not in {"phrase", "structure"}:
            continue
        pattern = str(c.get("pattern", "")).strip()
        if not pattern:
            continue
        cleaned.append(
            {
                "source": sample.name,
                "kind": kind,
                "pattern": pattern,
                "example_quote": str(c.get("example_quote", "")).strip(),
                "why_slop": str(c.get("why_slop", "")).strip(),
                "suggested_fix": str(c.get("suggested_fix", "")).strip(),
            }
        )
    return cleaned


CLUSTER_PROMPT = """\
You will receive a flat list of candidate slop patterns mined from many
samples. Different mining passes often phrase the same pattern differently.
Cluster them, count frequency, and emit proposed additions to the Stop Slop
skill for any cluster that appears in at least {min_frequency} distinct sources.

Candidates (JSON list):
{candidates}

For each cluster meeting the frequency threshold, return ONE entry. Return
ONLY a JSON object with this shape:

{{
  "additions": [
    {{
      "kind": "phrase" | "structure",
      "title": "<short heading for the new rule, e.g. 'I want to share... openers'>",
      "frequency": <int, number of distinct sources>,
      "rationale": "<one or two sentences explaining why this is a tell>",
      "examples": ["<quote 1>", "<quote 2>"],
      "fix": "<one sentence on how to rewrite>",
      "markdown_entry": "<exact markdown to append, formatted to match the style of phrases.md (for phrase) or structures.md (for structure). Include heading if it does not already exist below.>"
    }}
  ]
}}

Rules for the markdown_entry field:
- For phrases.md additions, use the same bullet-list style under an appropriate
  existing section, OR introduce a new "## " heading if no section fits.
- For structures.md additions, use the same "| Pattern | Problem |" table
  style under an existing section, OR introduce a new "## " heading.
- Keep the entry self-contained: it should be ready to append verbatim to the
  end of the file. Include a leading blank line.
- Do not repeat content that already exists in the skill.

Do not include any prose outside the JSON object.
"""


def cluster_and_draft(
    client: Any, bundle: Any, all_candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not all_candidates:
        return []
    prompt = CLUSTER_PROMPT.format(
        min_frequency=MIN_FREQUENCY,
        candidates=json.dumps(all_candidates, indent=2)[:60000],
    )
    raw = call_claude(client, bundle, prompt, max_tokens=4096)
    try:
        data = extract_json(raw)
    except ValueError as e:
        print(f"WARN: clustering pass failed: {e}", file=sys.stderr)
        return []
    additions = data.get("additions", []) if isinstance(data, dict) else []
    cleaned: list[dict[str, Any]] = []
    for a in additions:
        if not isinstance(a, dict):
            continue
        if a.get("kind") not in {"phrase", "structure"}:
            continue
        if not isinstance(a.get("frequency"), int) or a["frequency"] < MIN_FREQUENCY:
            continue
        entry = str(a.get("markdown_entry", "")).strip()
        if not entry:
            continue
        cleaned.append(
            {
                "kind": a["kind"],
                "title": str(a.get("title", "")).strip(),
                "frequency": a["frequency"],
                "rationale": str(a.get("rationale", "")).strip(),
                "examples": [str(x) for x in a.get("examples", []) if x],
                "fix": str(a.get("fix", "")).strip(),
                "markdown_entry": entry,
            }
        )
    return cleaned


def apply_additions(additions: list[dict[str, Any]]) -> list[Path]:
    phrase_entries = [a["markdown_entry"] for a in additions if a["kind"] == "phrase"]
    structure_entries = [a["markdown_entry"] for a in additions if a["kind"] == "structure"]

    changed: list[Path] = []

    if phrase_entries:
        path = REFERENCES_DIR / "phrases.md"
        original = path.read_text(encoding="utf-8")
        new = original.rstrip() + "\n\n" + "\n\n".join(e.strip() for e in phrase_entries) + "\n"
        path.write_text(new, encoding="utf-8")
        changed.append(path)

    if structure_entries:
        path = REFERENCES_DIR / "structures.md"
        original = path.read_text(encoding="utf-8")
        new = original.rstrip() + "\n\n" + "\n\n".join(e.strip() for e in structure_entries) + "\n"
        path.write_text(new, encoding="utf-8")
        changed.append(path)

    return changed


def format_pr_body(additions: list[dict[str, Any]], samples_used: int) -> str:
    lines = [
        f"Mined {len(additions)} new rule addition(s) from {samples_used} sample(s).",
        "",
        "Each addition appeared in at least "
        f"{MIN_FREQUENCY} distinct source(s) in the corpus.",
        "",
        "## Proposed additions",
        "",
    ]
    for a in additions:
        lines.append(f"### {a['title']} ({a['kind']}, frequency {a['frequency']})")
        lines.append("")
        if a["rationale"]:
            lines.append(a["rationale"])
            lines.append("")
        if a["examples"]:
            lines.append("Examples:")
            for ex in a["examples"][:4]:
                lines.append(f"- {ex}")
            lines.append("")
        if a["fix"]:
            lines.append(f"**Fix:** {a['fix']}")
            lines.append("")
    lines.append("---")
    lines.append("_Generated by `mine_rules.py`. Review carefully before merging._")
    return "\n".join(lines)


def gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_base_sha(repo: str, branch: str, token: str) -> str:
    r = requests.get(
        f"{GITHUB_API}/repos/{repo}/git/ref/heads/{branch}",
        headers=gh_headers(token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["object"]["sha"]


def create_branch(repo: str, branch: str, sha: str, token: str) -> None:
    r = requests.post(
        f"{GITHUB_API}/repos/{repo}/git/refs",
        headers=gh_headers(token),
        json={"ref": f"refs/heads/{branch}", "sha": sha},
        timeout=30,
    )
    if r.status_code == 422:
        # Branch exists; update it to point at base sha.
        r2 = requests.patch(
            f"{GITHUB_API}/repos/{repo}/git/refs/heads/{branch}",
            headers=gh_headers(token),
            json={"sha": sha, "force": True},
            timeout=30,
        )
        r2.raise_for_status()
        return
    r.raise_for_status()


def get_file_sha(repo: str, path: str, branch: str, token: str) -> str | None:
    r = requests.get(
        f"{GITHUB_API}/repos/{repo}/contents/{path}",
        headers=gh_headers(token),
        params={"ref": branch},
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("sha")


def put_file(
    repo: str, path: str, branch: str, content: str, message: str, token: str
) -> None:
    existing_sha = get_file_sha(repo, path, branch, token)
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha
    r = requests.put(
        f"{GITHUB_API}/repos/{repo}/contents/{path}",
        headers=gh_headers(token),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()


def open_pull_request(
    repo: str, head: str, base: str, title: str, body: str, token: str
) -> str:
    r = requests.post(
        f"{GITHUB_API}/repos/{repo}/pulls",
        headers=gh_headers(token),
        json={"title": title, "head": head, "base": base, "body": body, "draft": True},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["html_url"]


def main() -> int:
    samples = load_local_samples() + load_url_samples()
    if not samples:
        print("No samples in corpus/samples/ or corpus/sources.txt. Nothing to mine.")
        return 0

    if len(samples) > MAX_SAMPLES:
        print(f"Capping {len(samples)} samples to {MAX_SAMPLES}.")
        samples = samples[:MAX_SAMPLES]

    client = get_client()
    bundle = load_skill_bundle()

    all_candidates: list[dict[str, Any]] = []
    for s in samples:
        print(f"Mining {s.name}...")
        all_candidates.extend(find_candidates_in_sample(client, bundle, s))

    print(f"Collected {len(all_candidates)} raw candidate(s). Clustering...")
    additions = cluster_and_draft(client, bundle, all_candidates)
    if not additions:
        print("No additions met the frequency threshold. Nothing to PR.")
        return 0

    changed = apply_additions(additions)
    if not changed:
        print("No file changes after applying additions.")
        return 0

    print(f"Wrote {len(changed)} file(s): {[str(p.relative_to(REPO_ROOT)) for p in changed]}")

    if DRY_RUN:
        print("DRY RUN: skipping PR creation.")
        return 0

    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    today = dt.date.today().isoformat()
    branch = f"rule-mining/{today}"
    title = f"Rule mining: {len(additions)} proposed addition(s) ({today})"
    body = format_pr_body(additions, samples_used=len(samples))

    base_sha = get_base_sha(repo, BASE_BRANCH, token)
    create_branch(repo, branch, base_sha, token)
    for path in changed:
        rel = str(path.relative_to(REPO_ROOT))
        put_file(
            repo,
            rel,
            branch,
            path.read_text(encoding="utf-8"),
            f"Mine slop rules: update {rel}",
            token,
        )
    url = open_pull_request(repo, branch, BASE_BRANCH, title, body, token)
    print(f"Opened draft PR: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
