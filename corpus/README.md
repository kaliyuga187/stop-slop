# Corpus

Inputs for the rule miner (`.github/workflows/mine-rules.yml`).

Two input channels, both optional:

## `samples/`

Drop AI-generated prose into this directory as `.md` or `.txt` files. The miner
reads everything in here on each run. Empty files are ignored.

## `sources.txt`

One URL per line. The miner fetches each URL (`User-Agent: stop-slop-miner/1.0`)
and treats the response body as a sample. Lines starting with `#` are comments.
Each URL is truncated to 20KB to keep token use bounded.

## How it runs

The miner asks Claude what slop patterns appear in each sample that are *not*
already covered by `SKILL.md` + `references/`. Candidates are aggregated,
clustered across sources, and any cluster appearing in ≥ `MIN_FREQUENCY`
distinct sources (default 2) becomes a proposed rule addition. The workflow
opens a draft PR with the additions appended to `references/phrases.md` or
`references/structures.md`.

Trigger manually from the Actions tab (`Stop Slop Rule Mining` → `Run workflow`)
or wait for the weekly Monday 09:00 UTC cron.

## Seeded smoke-test samples

`samples/seed-*.md` are synthetic AI-prose samples written by Claude as a
smoke test for the mining pipeline. They are *not* a representative real-world
corpus — they exist so the miner has something to chew on for end-to-end
verification before real samples land. Replace or delete them once you have
real text to mine.

The four seeds (`seed-thought-leadership.md`, `seed-product-launch.md`,
`seed-personal-essay.md`, `seed-twitter-thread.md`) share several patterns
on purpose so the cross-sample clustering pass has material to find:

- `"Quick story:" / "Quick context:" / "Quick aside:"` micro-narrative openers
- `"Sound familiar?"` rhetorical-question transitions
- `"Hot take:" / "Unpopular opinion:"` opinion-disclaimer labels
- `"TL;DR: / "Bottom line: / "The takeaway:"` summary-tag closers
- `"It's [year] and..."` temporal scene-setters

A successful smoke run should produce a draft PR that proposes additions
covering some subset of those patterns.
