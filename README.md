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
| `/implement` | Implement a design plan in full and commit it, without a review pass |
| `/implement-and-review` | `/implement`, then iteratively review and fix the branch with a stronger model until it converges |
| `/babysit-pr` | Watch a PR's CI until it passes, dispatching a fixer agent to repair any failing checks |
| `/ship-issue` | Take a GitHub issue through design, plan review, implementation, independent review, and a pull request in one chain |
| `/autonomous-branch-review-loop` | `/branch-review-loop` with no round cap, each substantive finding's severity challenged, and trivial issues fixed in the round they appear |
| `/autonomous-design-review-loop` | `/design-review-loop` with no round cap, each substantive finding's severity challenged, and trivial issues fixed in the round they appear |
| `/ship-auto` | `/ship-issue` for an away-from-keyboard user: never prompts, takes recorded defaults, and reports the decisions it took, then babysits the PR's CI |

## Conventions

These skills establish a lightweight workflow convention:

- **`tasks/`** — active design plans
- **`tasks/completed/`** — plans that have been implemented
- **`CHANGELOG.md`** — the `/pr` skill updates the unreleased section, following the convention the project documents (e.g. appending at the end of a subject section)
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
`Skill` invocations: `/implement-and-review` = `implement` + `branch-review-loop` (strong-tier reviewer), and
`/ship-issue` = `design` → `design-review-loop` → `implement` → `branch-review-loop` → `pr`. The autonomous variants
(`/autonomous-branch-review-loop`, `/autonomous-design-review-loop`, `/ship-auto`) are thin wrappers that
invoke the base skill with an "autonomous mode" or "AFK mode" argument, whose behavior lives in the base skill.
Nothing is restated, so a change to any skill is inherited by everything built on it.

## Using other models

Skills name models by role, not brand: `{{coding}}` for well-specified, mechanical work (fixers,
the implementer, conflict resolvers) and `{{thinking}}` for judgment (the reviewer a composite
skill asks for). Each skill that spawns model-specific agents carries one canonical declaration that
binds the two roles to the aliases `sonnet` and `opus`; `scripts/validate.py` keeps it
byte-identical across skills and rejects model names anywhere else.

To run on other models:

1. **Remap the aliases** (preferred). Claude Code resolves `sonnet` and `opus` through
   `ANTHROPIC_DEFAULT_SONNET_MODEL` and `ANTHROPIC_DEFAULT_OPUS_MODEL`; point them at the models
   your Bedrock, Vertex, or gateway setup serves. No plugin edit needed.
2. **Edit the declaration.** Swap the two quoted values in each skill's "Model tiers" paragraph for
   another alias (`sonnet`, `opus`, `haiku`, `fable`), keeping the paragraph identical across
   skills so the validator passes.

Every alias in use has to resolve to a model your provider can serve: an alias it cannot serve fails
with `model_not_found` and is not retried. Aliases also resolve to different versions per provider.
The prompts were tuned on Claude models; results on others may vary. `/ship-auto` additionally pins
its session turn to the `opus` alias in its frontmatter (frontmatter cannot hold a placeholder), so
that alias must resolve too.

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
