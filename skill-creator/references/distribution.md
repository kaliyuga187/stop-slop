# Distribution

How to ship a skill, and the honest answer to "how do I monetize it".

## Install paths

A skill is a directory. There are three places it can live:

### 1. User-level (available in every session)

```
~/.claude/skills/<skill-name>/
```

Drop the directory there. Claude Code picks it up on next session start.

### 2. Project-level (scoped to one repo)

```
<repo>/.claude/skills/<skill-name>/
```

Commit it. Anyone who clones the repo gets the skill in that project.

### 3. Plugin marketplace (Claude Code plugins)

Package the skill inside a plugin and publish the plugin to a marketplace repo. The user installs with `/plugin install <name>`. Plugins can bundle skills, slash commands, hooks, and MCP servers together.

## Publishing to GitHub

The standard pattern:

```bash
git init
git add SKILL.md references/ README.md LICENSE
git commit -m "initial skill"
gh repo create my-skill --public --source=. --push
```

Tell people to install with:

```bash
git clone https://github.com/<you>/my-skill ~/.claude/skills/my-skill
```

That's it. No registration, no listing flow.

## On "monetization"

There is no Anthropic skill marketplace with payouts. As of 2026-05, skills are MIT-licensed source files distributed through GitHub or plugin marketplaces. Nobody is going to PayPal you for a `SKILL.md`.

What people do to make money adjacent to skills:

1. **Sell the work.** Use skills to deliver client projects faster. Charge for the project, not the skill.
2. **Sell the bundle.** Skills + custom hooks + MCP servers + onboarding for a team. Charge for setup and support.
3. **Sponsorship.** GitHub Sponsors on the skills repo if it gets traction. Realistic ceiling: low.
4. **Course / course-adjacent.** Teach people to build skills. Charge for the teaching, not the skills (which stay free).

What does *not* work:

- Listing a `SKILL.md` on Gumroad behind a paywall. Anyone who buys it can re-publish it. MIT or no, the artifact is too small to defend.
- Building a "skill marketplace" yourself. The distribution friction is near-zero (it's a markdown file in a repo). There's no rent to extract.
- Obfuscating the skill. Skills are read by Claude as text. There is nothing to encrypt.

The boring, accurate framing: skills are documentation that Claude executes. Treat them like open-source docs. The value is in what you build *with* them.

## Versioning

Tag releases on GitHub. Users who want a stable version pin to a tag:

```bash
git clone --branch v1.2.0 https://github.com/<you>/my-skill ~/.claude/skills/my-skill
```

Bump the version in `SKILL.md` frontmatter (`metadata.version: 1.2.0`) so it shows up in the file too.
