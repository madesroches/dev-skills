# Changelog

All notable changes to the `dev-skills` plugin are documented in this file.

## Unreleased

- `ship-issue` reminds the user up front to give an explicit push instruction when the invocation lacks one, so the final push (and CI) isn't gated by the permission layer

## [1.9.0] - 2026-07-04

- Stop `ship-issue` from halting after design: run the chain autonomously, pausing only on hard blockers
- Open questions are no longer a stop condition — `design-review` resolves them from the codebase
- `design-review` treats plan open questions as candidates to answer; loop folds answers in or flags user-decision ones

## [1.8.0] - 2026-07-04

- Add `ship-issue` skill: chain design → design-review-loop → implement-and-review → pr for a GitHub issue
- Ask about dirty tree before branching; handle detached HEAD in preflight
- Allow `AskUserQuestion` and ask before baseline-committing a dirty tree

## [1.7.0] - 2026-07-04

- Use merge-base diffs, detect base branch, forbid AI attribution everywhere
- Fix wording nits in `implement-and-review`; sync marketplace description
- Guard against running `implement-and-review` on the base branch
- State no-attribution rule as `implement-and-review`'s own
- Describe all `implement-and-review` deviations in CLAUDE.md
- Resolve review-skill path in preflight; clarify opus override precedence

## [1.6.0] - 2026-07-04

- Add `implement-and-review` skill

## [1.5.0] - 2026-07-03

- Tighten skill permissions and loop round-cap wording
- Use unique per-invocation commit-msg scratch files in loop skills
- Pin fixer agents to sonnet in review loop skills

## [1.4.0] - 2026-06-23

- Add documentation gap check to `design-review` skill
- Fix loop-skill commit-msg write path to use `/tmp`

## [1.3.0] - 2026-06-13

- Print fix summary before fixer agent in loop skills
- Add loop skills to README skill table

## [1.2.0] - 2026-05-26

- Make loop-skill round commits meaningful and checker-safe

## [1.1.0] - 2026-05-26

- Harden skill-path resolution against trailing slash

## [1.0.1] - 2026-05-26

- Add `design-review-loop` and `branch-review-loop` skills; simplify review Phase 5
- Fix loop skills passing relative path to reviewer subagent
- Add `.gitignore` for local Claude settings and editor files
- Add CLAUDE.md with plugin architecture and conventions
- Switch license from MIT to Apache 2.0
- Add `marketplace.json` for plugin registry

## [1.0.0] - 2026-03-21

- Initial release: `pr`, `design`, `design-review`, and `branch-review` skills
