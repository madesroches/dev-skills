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
| `/implement-and-review` | Implement a design plan, commit it, then iteratively review and fix the branch with a stronger model until it converges |
| `/ship-issue` | Take a GitHub issue through design, plan review, implementation, independent review, and a pull request in one chain |

## Conventions

These skills establish a lightweight workflow convention:

- **`tasks/`** — active design plans
- **`tasks/completed/`** — plans that have been implemented
- **`CHANGELOG.md`** — the `/pr` skill updates the unreleased section
- **Verification tiers** — a plan's `## Testing Strategy` covers everything a unit test can reach
  (which is the default for anything callable with constructed inputs) plus regression tests for
  bugs seen in the wild; its `## Manual Verification` section holds the runnable-by-hand checks
  that aren't worth maintaining as tests. The review skills treat that section as a recorded
  decision rather than a coverage gap, and `/pr` copies it into the PR's test plan

## How the skills compose

The review skills follow a **candidate → parallel verification → report** pattern: identify
potential issues, verify each against real code with parallel Explore agents, and report only
confirmed ones, classified by severity. The loop skills (`/design-review-loop`,
`/branch-review-loop`) wrap a review skill in an autonomous review → fix → commit cycle with a
fresh reviewer each round, then close out whatever the loop left behind — trivial issues and any
still-open findings — in a final unreviewed pass. The composite skills chain the others via direct
`Skill` invocations: `/implement-and-review` = implement + `branch-review-loop` (opus reviewer), and
`/ship-issue` = `design` → `design-review-loop` → `implement-and-review` → `pr`. Nothing is
restated, so a change to any skill is inherited by everything built on it.

## Installation

This repo is its own plugin marketplace. In Claude Code:

```
/plugin marketplace add madesroches/dev-skills
/plugin install dev-skills@dev-skills
```

For a local checkout, use the path instead:

```
/plugin marketplace add /path/to/dev-skills
/plugin install dev-skills@dev-skills
```

## How `/pr` discovers checks

Instead of hardcoding lint/test commands, the `/pr` skill reads your project's `CLAUDE.md` (and `AI_GUIDELINES.md` if present) to discover which commands to run. It then cross-references `git diff --stat` to determine which areas changed and runs only the relevant checks in parallel.

If no `CLAUDE.md` exists or no commands are documented for a changed area, it asks you what to run.
