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
