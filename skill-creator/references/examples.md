# Examples

Three skills. The first is the smallest useful shape. The second shows when to add reference files. The third is the trap: a "skill" that should have been a hook.

## Example 1: Thin skill (no references)

A skill for converting curl commands into TypeScript fetch calls.

```markdown
---
name: curl-to-fetch
description: Convert curl commands into TypeScript fetch() calls. Use when the user pastes a curl command and asks for a JS or TS version.
metadata:
  trigger: User pastes a curl command and asks to translate it
  author: Jane Doe
---

# Curl to Fetch

Convert a `curl` command into an equivalent TypeScript `fetch()` call.

## Rules

1. **Preserve method, headers, and body.** Map `-X`, `-H`, `-d` and `--data` to the `fetch` init object.
2. **Use the typed `RequestInit` shape.** Headers as a plain object. Body as a string for `application/json`, `FormData` for multipart.
3. **Return the parsed JSON.** Wrap in `async/await`. Throw on non-2xx.
4. **Skip auth secrets.** Replace bearer tokens and API keys with `process.env.X` references.

## Output shape

```ts
const res = await fetch(url, { method, headers, body });
if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
return res.json();
```

## License

MIT
```

That's a complete skill. No reference files needed.

## Example 2: Medium skill (with references)

A skill for writing Postgres migrations safely.

```
pg-migrate/
├── SKILL.md
└── references/
    ├── locking.md          # Per-statement lock matrix
    ├── backfill-patterns.md
    └── checklist.md
```

The `SKILL.md` lists 6 rules and a pre-flight checklist. The reference files hold the lock matrix (a 40-row table), three backfill patterns with code, and a deploy-day checklist. Inlining any of those would bloat the main file.

Rule of thumb: if a section is over 30 lines and mostly data or examples, move it.

## Example 3: This should be a hook, not a skill

A user asks: "I want a skill that runs `pnpm test` after every code change."

That's not a skill. Skills run when Claude decides to load them. This wants to fire on a deterministic event (file write). Use a `PostToolUse` hook in `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "pnpm test" }]
      }
    ]
  }
}
```

When the user describes the trigger as "every time", "after every", "on save", or "automatically", that's a hook. Skills are for *what to do* once Claude is engaged, not *when* to do it.

## Anti-patterns

- **The kitchen-sink skill.** One `SKILL.md` covering "all our coding standards". Split it. Each skill should have one job.
- **The diary.** Notes from a session dumped into a `SKILL.md`. Cut hard. Anything Claude wouldn't act on is dead weight.
- **The marketing brochure.** "This powerful skill empowers your team to..." Cut. State what it does.
