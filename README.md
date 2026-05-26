# dev-skills

Development workflow skills for Claude Code: PR creation, design planning, and code review.

## Skills

| Skill | Description |
|-------|-------------|
| `/pr` | Run project lints/tests (auto-discovered from CLAUDE.md), manage plan files, update changelog, and create a GitHub PR |
| `/design` | Research the codebase and write a design plan to `tasks/` |
| `/design-review` | Review a design plan document, verify issues against real code |
| `/design-review-loop` | Iteratively review and fix a design plan until it converges |
| `/branch-review` | Code review the current branch diff with verified-only findings |
| `/branch-review-loop` | Iteratively review and fix the current branch until it converges |

## Conventions

These skills establish a lightweight workflow convention:

- **`tasks/`** — active design plans
- **`tasks/completed/`** — plans that have been implemented
- **`CHANGELOG.md`** — the `/pr` skill updates the unreleased section

## Installation

Add the plugin to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "plugins": [
    "/path/to/dev-skills"
  ]
}
```

Or if published to a marketplace, install via the Claude Code plugin manager.

## How `/pr` discovers checks

Instead of hardcoding lint/test commands, the `/pr` skill reads your project's `CLAUDE.md` (and `AI_GUIDELINES.md` if present) to discover which commands to run. It then cross-references `git diff --stat` to determine which areas changed and runs only the relevant checks in parallel.

If no `CLAUDE.md` exists or no commands are documented for a changed area, it asks you what to run.
