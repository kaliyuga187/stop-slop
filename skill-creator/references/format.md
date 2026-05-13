# SKILL.md Format

## Frontmatter

YAML between two `---` lines at the top of the file.

```yaml
---
name: my-skill
description: One sentence: what it does and when to load it.
metadata:
  trigger: Plain-language description of when this fires
  author: Your Name (https://your-url)
---
```

### Required fields

- **`name`**: Kebab-case. Matches the directory name. Under 30 characters.
- **`description`**: One sentence. Both the *what* and the *when*. The harness reads this to decide whether to surface the skill, so put the trigger phrase in here.

### Optional fields

- **`metadata.trigger`**: Longer trigger description for human readers.
- **`metadata.author`**: Name and URL.
- **`allowed-tools`**: List of tools the skill is permitted to call. Omit if any tool is fine.

## Body

Markdown. No fixed schema, but skills that work well share a shape:

1. **One-line summary** under the H1.
2. **When to load this skill**: explicit triggers and anti-triggers (when *not* to load).
3. **Core rules**: numbered, imperative, one short paragraph each. 3 to 8 of them.
4. **Quick checks**: a bulleted checklist the skill runs before output. Optional.
5. **Examples**: link out to `references/examples.md` rather than inlining long examples.
6. **License**: one line.

## Reference files

Anything long (phrase lists, example pairs, structural patterns) goes in `references/*.md`. The skill links to them with relative markdown links: `[references/foo.md](references/foo.md)`. Claude reads them on demand, so the main `SKILL.md` stays small.

## Voice rules (for skills in this repo)

This repo houses the `stop-slop` skill, so any new skill here must pass its own checks:

- No adverbs.
- No em dashes.
- Active voice. Human subject doing something.
- No throat-clearing openers. No "here's what this skill does".
- Vary sentence length.

## Common mistakes

- **Description is a tagline, not a trigger.** "A powerful skill for writers" tells the harness nothing. Write what the user will say or do.
- **Inlined 500-line phrase list.** Move it to `references/`.
- **Frontmatter only, no body.** The body is where the actual instructions live.
- **Tool restrictions copied from another skill.** Set `allowed-tools` only if the skill needs to be locked down.
- **No "when not to load" guidance.** Leads to the skill firing on every adjacent task.
