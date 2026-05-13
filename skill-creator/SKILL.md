---
name: skill-creator
description: Build new Claude skills. Use when the user wants to package a workflow, prompt pattern, or domain knowledge into a reusable SKILL.md.
metadata:
  trigger: User says "make a skill", "package this as a skill", "write a SKILL.md", or describes a recurring task they want Claude to handle the same way every time
  author: Hardik Pandya (https://hvpandya.com)
---

# Skill Creator

Turn a workflow into a skill: a `SKILL.md` plus optional reference files that Claude loads on demand.

## When to load this skill

The user wants to capture a repeatable task as a reusable artifact. Signals: "I keep telling you to do X", "make this a skill", "save this as instructions", "package this for the team".

If they want a one-off automation that runs without being asked, that's a hook in `settings.json`, not a skill. Redirect.

## What a skill is

A directory with one required file:

```
my-skill/
├── SKILL.md              # Frontmatter + instructions
└── references/           # Optional. Loaded on demand by the skill.
    └── *.md
```

`SKILL.md` has YAML frontmatter (`name`, `description`, optional `metadata`) and markdown instructions. See [references/format.md](references/format.md).

## How to build one

Run a short interview, then write the file. Five questions:

1. **Name.** Kebab-case, under 30 characters. Matches the directory.
2. **Trigger.** One sentence. When should Claude load this skill? What does the user say or do?
3. **Core rules.** 3 to 8 numbered rules. Each is one short paragraph. Imperative voice.
4. **Quick checks.** A bulleted list the skill can run before delivering output. Optional.
5. **References.** What needs its own file? Long lists, examples, edge cases. Each becomes `references/<name>.md` and gets linked from `SKILL.md`.

Skip anything the user can't answer. A small skill is better than a padded one.

## Output rules

- Write `SKILL.md` to match this repo's voice: direct, no adverbs, no em dashes, active voice. The `stop-slop` skill in the parent directory is the style reference.
- Frontmatter `description` must include both *what the skill does* and *when to load it*. The harness uses this to decide whether to surface the skill.
- Link reference files with relative paths: `[references/foo.md](references/foo.md)`.
- No marketing copy. No "this powerful skill helps you...". State what it does.
- Default to no comments inside markdown. The text is the artifact.

## Examples

See [references/examples.md](references/examples.md) for a thin skill, a medium skill, and one that should have been a hook instead.

## Distribution

Skills are MIT-licensed source files. There is no Anthropic marketplace and no payment system. Publish to GitHub, share the URL, install with `git clone`. See [references/distribution.md](references/distribution.md) for the install paths and what "monetization" looks like in practice (spoiler: sell the work built on top of skills, not the skills).

## License

MIT
