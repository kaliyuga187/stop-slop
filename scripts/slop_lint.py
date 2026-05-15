"""Run the Stop Slop skill against a pull request and post inline review comments.

Inputs (env):
    GITHUB_TOKEN          - GitHub Actions token, used to read the diff and post review
    GITHUB_REPOSITORY     - "owner/repo"
    GITHUB_EVENT_PATH     - path to the event payload JSON (pull_request event)
    ANTHROPIC_API_KEY     - Claude API key
    ANTHROPIC_MODEL       - optional, defaults to claude-sonnet-4-6
    SLOP_LINT_DRY_RUN     - if "1", print the review instead of posting

The linter is advisory: it always posts COMMENT, never REQUEST_CHANGES.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from _shared import call_claude, extract_json, get_client, load_skill_bundle

GITHUB_API = "https://api.github.com"

# Files the linter should never review. references/*.md catalog the patterns
# by design, and corpus/*.md is intentionally sloppy mining input.
SKIP_FILES = {"LICENSE", "CHANGELOG.md"}
SKIP_PREFIXES = ("references/", "corpus/")
OPT_OUT_MARKER = "<!-- slop-lint: skip -->"


@dataclass
class Hunk:
    """A contiguous block of changed lines in the new file."""

    start_line: int
    lines: list[tuple[int, str]]  # (line_number_in_new_file, text)


@dataclass
class ChangedFile:
    path: str
    hunks: list[Hunk]


def gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def load_event() -> dict[str, Any]:
    path = os.environ["GITHUB_EVENT_PATH"]
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_pr_files(repo: str, pr_number: int, token: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page = 1
    while True:
        r = requests.get(
            f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/files",
            headers=gh_headers(token),
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        files.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return files


def fetch_file_at_ref(repo: str, path: str, ref: str, token: str) -> str | None:
    r = requests.get(
        f"{GITHUB_API}/repos/{repo}/contents/{path}",
        headers={**gh_headers(token), "Accept": "application/vnd.github.raw"},
        params={"ref": ref},
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.text


def parse_patch_to_hunks(patch: str) -> list[Hunk]:
    """Parse a unified diff patch into hunks of added/context lines in the new file.

    GitHub's `files` endpoint returns per-file patches. We only care about the
    new-file line numbers, so we walk the patch tracking the current new-file
    line number and collect added lines (prefix '+') into hunks.
    """
    hunks: list[Hunk] = []
    current: list[tuple[int, str]] = []
    current_start: int | None = None
    new_line = 0

    for raw in patch.splitlines():
        if raw.startswith("@@"):
            if current and current_start is not None:
                hunks.append(Hunk(current_start, current))
            current = []
            current_start = None
            # @@ -a,b +c,d @@
            try:
                plus = raw.split("+", 1)[1].split(" ", 1)[0]
                new_line = int(plus.split(",", 1)[0])
            except (IndexError, ValueError):
                new_line = 0
            continue

        if not raw:
            continue

        marker, body = raw[0], raw[1:]
        if marker == "+" and not raw.startswith("+++"):
            if current_start is None:
                current_start = new_line
            current.append((new_line, body))
            new_line += 1
        elif marker == "-" and not raw.startswith("---"):
            # Deletion: doesn't advance new-file line count.
            pass
        elif marker == " ":
            # Context: close out the current hunk so we don't bundle unrelated
            # additions, but still advance the new-line counter.
            if current and current_start is not None:
                hunks.append(Hunk(current_start, current))
                current = []
                current_start = None
            new_line += 1

    if current and current_start is not None:
        hunks.append(Hunk(current_start, current))

    return hunks


def should_review(file_entry: dict[str, Any]) -> bool:
    path = file_entry["filename"]
    if file_entry.get("status") == "removed":
        return False
    if not path.endswith(".md"):
        return False
    if path in SKIP_FILES:
        return False
    if any(path.startswith(p) for p in SKIP_PREFIXES):
        return False
    return True


REVIEW_PROMPT_TEMPLATE = """\
You are reviewing changed prose from a markdown file in a pull request. Apply
the Stop Slop skill to flag specific violations.

File: `{path}`

Changed lines (line numbers refer to the file's NEW state):

{numbered_hunks}

Return ONLY a single JSON object with this exact shape:

{{
  "findings": [
    {{
      "line": <int, line number in the new file where the issue appears>,
      "quote": "<the offending text, verbatim, kept short>",
      "rule": "<which rule from the skill it violates, e.g. 'Adverb (phrases.md)' or 'Binary contrast (structures.md)'>",
      "suggestion": "<a concrete rewrite that obeys the skill>"
    }}
  ],
  "score": {{
    "directness": <int 1-10>,
    "rhythm": <int 1-10>,
    "trust": <int 1-10>,
    "authenticity": <int 1-10>,
    "density": <int 1-10>
  }},
  "summary": "<one sentence describing the overall slop level of these changes>"
}}

Rules for findings:
- Only flag lines from the changed lines shown above. Do not invent line numbers.
- Be specific. Quote the exact words. Suggest a concrete rewrite, not vague advice.
- Skip code blocks, tables, frontmatter, and bare links. Prose only.
- If a line has no slop, do not include it.
- Cap findings at 15 per file. Prioritize the worst offenders.

Do not include any prose outside the JSON object.
"""


def build_numbered_hunks(hunks: list[Hunk]) -> str:
    blocks: list[str] = []
    for h in hunks:
        lines = "\n".join(f"{ln:>5}: {text}" for ln, text in h.lines)
        blocks.append(lines)
    return "\n---\n".join(blocks)


@dataclass
class FileReview:
    path: str
    findings: list[dict[str, Any]]
    score: dict[str, int]
    summary: str


def review_file(client: Any, bundle: Any, path: str, hunks: list[Hunk]) -> FileReview | None:
    if not hunks:
        return None
    prompt = REVIEW_PROMPT_TEMPLATE.format(
        path=path,
        numbered_hunks=build_numbered_hunks(hunks),
    )
    raw = call_claude(client, bundle, prompt, max_tokens=2048)
    try:
        data = extract_json(raw)
    except ValueError as e:
        print(f"WARN: failed to parse review JSON for {path}: {e}", file=sys.stderr)
        return None

    findings = data.get("findings", []) if isinstance(data, dict) else []
    score = data.get("score", {}) if isinstance(data, dict) else {}
    summary = data.get("summary", "") if isinstance(data, dict) else ""

    valid_lines = {ln for h in hunks for ln, _ in h.lines}
    cleaned: list[dict[str, Any]] = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        line = f.get("line")
        if not isinstance(line, int) or line not in valid_lines:
            continue
        cleaned.append(
            {
                "line": line,
                "quote": str(f.get("quote", "")).strip(),
                "rule": str(f.get("rule", "")).strip() or "Stop Slop rule",
                "suggestion": str(f.get("suggestion", "")).strip(),
            }
        )

    return FileReview(path=path, findings=cleaned, score=score, summary=summary)


def format_comment(finding: dict[str, Any]) -> str:
    quote = finding["quote"]
    rule = finding["rule"]
    suggestion = finding["suggestion"]
    body = f"**Stop Slop:** {rule}\n\n"
    if quote:
        body += f"> {quote}\n\n"
    if suggestion:
        body += f"**Suggested rewrite:** {suggestion}\n"
    return body


def aggregate_score(reviews: list[FileReview]) -> dict[str, Any]:
    if not reviews:
        return {}
    dims = ["directness", "rhythm", "trust", "authenticity", "density"]
    averages: dict[str, float] = {}
    for d in dims:
        values = [r.score.get(d) for r in reviews if isinstance(r.score.get(d), int)]
        if values:
            averages[d] = sum(values) / len(values)
    if not averages:
        return {}
    total = sum(averages.values())
    return {"per_dimension": averages, "total": total}


def format_summary_body(reviews: list[FileReview]) -> str:
    if not reviews:
        return "No reviewable prose changes detected. Stop Slop skipped."

    lines = ["## Stop Slop review", ""]
    total_findings = sum(len(r.findings) for r in reviews)
    lines.append(f"Reviewed {len(reviews)} file(s), found {total_findings} potential slop pattern(s).")
    lines.append("")

    agg = aggregate_score(reviews)
    if agg:
        lines.append("### Average score across changed files")
        lines.append("")
        lines.append("| Dimension | Score |")
        lines.append("|-----------|-------|")
        for dim, val in agg["per_dimension"].items():
            lines.append(f"| {dim.capitalize()} | {val:.1f} / 10 |")
        lines.append(f"| **Total** | **{agg['total']:.1f} / 50** |")
        lines.append("")
        if agg["total"] < 35:
            lines.append("Aggregate is below 35/50. The skill recommends revision.")
            lines.append("")

    lines.append("### Per-file summary")
    lines.append("")
    for r in reviews:
        s = r.summary or "(no summary)"
        lines.append(f"- **`{r.path}`** — {len(r.findings)} finding(s). {s}")

    lines.append("")
    lines.append("---")
    lines.append("_Advisory review. This check never blocks merge._")
    return "\n".join(lines)


def post_review(
    repo: str,
    pr_number: int,
    commit_sha: str,
    token: str,
    reviews: list[FileReview],
) -> None:
    comments: list[dict[str, Any]] = []
    for review in reviews:
        for finding in review.findings:
            comments.append(
                {
                    "path": review.path,
                    "line": finding["line"],
                    "side": "RIGHT",
                    "body": format_comment(finding),
                }
            )

    payload = {
        "commit_id": commit_sha,
        "body": format_summary_body(reviews),
        "event": "COMMENT",
        "comments": comments,
    }

    if os.environ.get("SLOP_LINT_DRY_RUN") == "1":
        print(json.dumps(payload, indent=2))
        return

    r = requests.post(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/reviews",
        headers=gh_headers(token),
        json=payload,
        timeout=30,
    )
    if r.status_code >= 300:
        print(f"GitHub API error {r.status_code}: {r.text}", file=sys.stderr)
        r.raise_for_status()


def main() -> int:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    event = load_event()

    pr = event.get("pull_request") or {}
    pr_number = pr.get("number")
    commit_sha = pr.get("head", {}).get("sha")
    if not pr_number or not commit_sha:
        print("Event has no pull_request.number / head.sha; nothing to do.", file=sys.stderr)
        return 0

    # Missing key is a setup state, not a slop verdict. The linter is advisory
    # and must not block merge, so we exit cleanly with a console note.
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set. Skipping Stop Slop review. "
            "Add the secret in repo Settings -> Secrets and variables -> Actions.",
            file=sys.stderr,
        )
        return 0

    files = fetch_pr_files(repo, pr_number, token)
    targets: list[ChangedFile] = []
    for entry in files:
        if not should_review(entry):
            continue
        patch = entry.get("patch")
        if not patch:
            continue
        contents = fetch_file_at_ref(repo, entry["filename"], commit_sha, token)
        if contents and OPT_OUT_MARKER in contents:
            continue
        hunks = parse_patch_to_hunks(patch)
        if hunks:
            targets.append(ChangedFile(path=entry["filename"], hunks=hunks))

    if not targets:
        post_review(repo, pr_number, commit_sha, token, [])
        return 0

    client = get_client()
    bundle = load_skill_bundle()

    reviews: list[FileReview] = []
    for tgt in targets:
        review = review_file(client, bundle, tgt.path, tgt.hunks)
        if review:
            reviews.append(review)

    post_review(repo, pr_number, commit_sha, token, reviews)
    return 0


if __name__ == "__main__":
    sys.exit(main())
