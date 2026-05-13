# Skill Creator

A skill for building Claude skills.

## What this is

You have a workflow you keep re-explaining to Claude. Package it once as a skill and Claude loads it on demand.

This skill runs the interview, writes the `SKILL.md`, and tells you where to put it.

## Skill Structure

```
skill-creator/
├── SKILL.md                    # Core instructions
├── references/
│   ├── format.md               # SKILL.md frontmatter + structure rules
│   ├── examples.md             # Thin, medium, and "should be a hook" examples
│   └── distribution.md         # Install paths and the truth about monetization
├── README.md
└── LICENSE
```

## Quick start

**Claude Code:** Drop this folder into `~/.claude/skills/skill-creator/` or commit it under `.claude/skills/skill-creator/` in a repo.

**Plugin install:** Bundle inside a plugin and publish to a marketplace, then `/plugin install`.

## What it does

- Runs a five-question interview to scope the skill
- Writes a `SKILL.md` with valid frontmatter and the right shape
- Splits long sections into `references/*.md` files
- Enforces the `stop-slop` voice rules so the skill doesn't read like AI

## What it won't do

- Post your skill to a paid store. None exists. See `references/distribution.md`.
- Set up automation that runs at session end. That's a hook, not a skill.
- Sell your skill for you. Skills are MIT documentation. The money is in the work built on top.

## Author

[Hardik Pandya](https://hvpandya.com)

## License

MIT.
