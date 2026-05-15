# Stop Slop

A skill for removing AI tells from prose.

<img width="3840" height="2160" alt="G-Yg4RVbIAAhVxW" src="https://github.com/user-attachments/assets/902afc15-1f40-4a9d-af24-8cd67afb8ebf" />

## What this is

AI writing has patterns. Predictable phrases, structures, rhythms. This skill teaches Claude (or any LLM) to catch and remove them.

## Skill Structure

```
stop-slop/
├── SKILL.md              # Core instructions
├── references/
│   ├── phrases.md        # Phrases to remove
│   ├── structures.md     # Structural patterns to avoid
│   └── examples.md       # Before/after transformations
├── README.md
└── LICENSE
```

## Quick start

**Claude Code:** Add this folder as a skill.

**Claude Projects:** Upload `SKILL.md` and reference files to project knowledge.

**Custom instructions:** Copy core rules from `SKILL.md`.

**API calls:** Include `SKILL.md` in your system prompt. Reference files load on demand.

## What it catches

**Banned phrases** - Throat-clearing openers, emphasis crutches, business jargon, all adverbs, vague declaratives, meta-commentary. See `references/phrases.md`.

**Structural clichés** - Binary contrasts, negative listings, dramatic fragmentation, rhetorical setups, false agency, narrator-from-a-distance voice, passive voice. See `references/structures.md`.

**Sentence-level rules** - No Wh- sentence starters, no em dashes, no staccato fragmentation, no lazy extremes, active voice required.

## Scoring

Rate 1-10 on each dimension:

| Dimension | Question |
|-----------|----------|
| Directness | Statements or announcements? |
| Rhythm | Varied or metronomic? |
| Trust | Respects reader intelligence? |
| Authenticity | Sounds human? |
| Density | Anything cuttable? |

Below 35/50: revise.

## Automation

Two GitHub Actions wrap the skill:

**`Stop Slop Lint`** (`.github/workflows/slop-lint.yml`) runs on every PR that
touches `*.md`. It sends the changed prose to Claude with the skill bundle
attached, then posts a single review with inline rewrite suggestions and a
1-10 score across the five rubric dimensions. Advisory only — never blocks
merge. `references/*.md` and `LICENSE` are skipped, since the references
catalog the patterns by design. Add `<!-- slop-lint: skip -->` to a file to opt
it out individually.

**`Stop Slop Rule Mining`** (`.github/workflows/mine-rules.yml`) runs weekly
(Monday 09:00 UTC) and on-demand from the Actions tab. It reads AI-prose
samples from `corpus/samples/*.{md,txt}` and URLs in `corpus/sources.txt`,
asks Claude to surface patterns not already covered by the rule set, clusters
them across samples, and opens a draft PR with additions to
`references/phrases.md` / `references/structures.md` for any pattern appearing
in at least two distinct sources.

Both workflows require an `ANTHROPIC_API_KEY` repository secret. Model
defaults to `claude-sonnet-4-6`; override via the `ANTHROPIC_MODEL` env in the
workflow file.

## Author

[Hardik Pandya](https://hvpandya.com)

## License

MIT. Use freely, share widely.
