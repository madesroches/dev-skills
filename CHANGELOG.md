# Changelog

All notable changes to the `dev-skills` plugin are documented in this file.

## [1.19.0] - 2026-08-26

- `pr` now moves a plan's associated `tasks/<slug>_mockups/` folder to `tasks/completed/` alongside the plan file, instead of leaving it behind in `tasks/`

## [1.18.0] - 2026-08-17

- Both review skills now judge whether tests earn their cost, not just whether tests exist: a new candidate category flags live-DB/real-service/network/container-backed tests for logic a unit test would cover fully, integration tests that only assert pure-function behavior, tests duplicating existing coverage, tests asserting their own mocks, and heavyweight fixtures added for a change that doesn't touch the dependency they exercise
- Each has a matching verification step that requires proving the cheap test couldn't catch it *and* that a cheaper seam already exists in the repo — dismissing the candidate when the real dependency is itself under test (schema, migration, driver, wire format, transaction semantics) or when building a seam would cost more than the test saves
- `design-review`'s "no integration coverage" gap is scoped to where components genuinely interact, so it no longer reads as a blanket push for heavier tests

## [1.17.0] - 2026-08-07

- `design` adds a Phase 4 that builds self-contained HTML mockups for features with a strong UX/UI component, styled to match the app's existing fonts/colors/components; when multiple layouts are equally valid it builds 2-3 options instead of picking one, and the plan's new Mockups section links to them
- Mockups are local files only — the skill never uses the Artifact tool to publish them

## [1.16.0] - 2026-07-30

- Both loop skills now end with a finalize pass that fixes everything the loop left behind — the trivial issues it skips each round, plus any substantive issues still open when it stops on cap/non-convergence/oscillation — and commits it (`design-review-loop` still leaves `needs user decision` questions for the user)
- `implement-and-review` drops its own finalize phase; that cleanup is now the review loop's job, so the skill is again a pure composition with no deviation
- `ship-issue` reports each loop's finalize outcome instead of assuming leftovers get carried forward

## [1.15.0] - 2026-07-29

- Remove the loop skills' preflight warning about `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` — a depth of 2 increases token use too much for some use cases to recommend by default

## [1.14.0] - 2026-07-23

- Parameterize `design-review-loop`'s reviewer model the same way `branch-review-loop` already is, so callers can request a stronger model for plan review
- Move severity classification and the structured issue format (severity/summary/location/why/fix) into `branch-review` and `design-review` Phase 4; the loop skills now consume that contract instead of restating it
- `design-review` reports open questions needing a user decision as their own category instead of shoehorning them into `trivial`
- Add documentation-gap candidate to `branch-review`, matching `design-review`
- `ship-issue` verifies an existing feature branch actually references the issue before piling commits onto it, asking otherwise
- Make `design-review`'s dependency-version lookups best-effort so a blocked network command can't stall an autonomous loop
- `/pr` handles a diverged/behind branch explicitly at push time: stop and report, never force-push
- Add `scripts/validate.py` and a GitHub Actions workflow checking frontmatter, version↔changelog sync, manifest description sync, README coverage, and tool declarations
- Note in both loop skills that they are deliberate mirrors and shared-mechanics changes must be applied to both
- Update README installation instructions to the current plugin marketplace flow
- Backfill changelog entries for 1.10.0–1.13.0

## [1.13.0] - 2026-07-23

- Parameterize `branch-review-loop`'s reviewer model (optional override, same mechanism as the round cap)
- `implement-and-review` invokes `branch-review-loop` directly via the `Skill` tool (opus reviewer, round cap 10) instead of reading its file as text with deviations

## [1.12.0] - 2026-07-23

- Warn in loop-skill preflight when `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` < 2, since the reviewer's parallel verification needs nested subagent spawning

## [1.11.0] - 2026-07-09

- `branch-review` treats lint suppressions introduced by the diff (`#[allow(clippy::...)]` etc.) as candidates and verifies whether each hides a real concern

## [1.10.0] - 2026-07-06

- `design-review` scrutinizes new dependencies on two axes: value earned and whether the latest stable version is pinned
- Raise `design-review-loop` round cap to 10 in `ship-issue`
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
