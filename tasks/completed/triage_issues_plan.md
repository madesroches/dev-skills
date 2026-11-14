# Triage Issues (Bot-Ready Labeling) Plan

## Overview
A new `/triage-issues` skill that scans a project's open GitHub issues and applies a `bot-ready`
label to the ones a conservative implementation bot (`/ship-issue`, `/ship-auto`) has a good chance
of completing without guessing. The call is a judgment call, so each issue is assessed by a
`{{thinking}}`-tier agent. An issue is ruled out if it has a UX component, has an unmet
dependency, is high-risk, or is not described well enough for the bot to settle every decision it will face.

## Current State
- No skill touches issue triage. `ship-issue` (`skills/ship-issue/SKILL.md`) takes one issue number
  and assumes the user already picked a suitable one; nothing tells a user which issues are safe to
  hand to `/ship-auto`.
- Precedent for the shape: `babysit-pr` and the review loops use a thin orchestrator that does the
  `gh`/`git` work and dispatches fresh `Task` agents on a model tier (`{{coding}}`/`{{thinking}}`)
  for the actual work. `scripts/validate.py` enforces the skill checks (see Testing Strategy).
- `validate.py` check 7 requires the canonical "Model tiers" paragraph in any skill using a
  placeholder.

## Design

**Name and arguments.** `skills/triage-issues/SKILL.md`, `argument-hint: "[— label NAME] [— limit N] [— recheck] [— dry run]"`.
- `label NAME` — label to apply, default `bot-ready`.
- `limit N` — max issues judged per run, default 30 (each costs a thinking-tier agent); applied after filtering, oldest first.
- `recheck` — also re-assess issues that already carry the label.
- `dry run` — report verdicts, change nothing on GitHub.

The skill is autonomous (no prompts) and only ever adds the label, except with `recheck` (below).

**Roles.**
- **Orchestrator** (main context): lists issues, gathers mechanical facts, dispatches judges,
  applies labels, writes the report. It does not judge issues itself.
- **Judge agent**: one fresh `Task` agent per issue (`general-purpose`, `model` = `{{thinking}}`),
  run in parallel batches of 5. One agent per issue keeps verdicts independent. A judge reads the
  issue, **all** its comments (they often resolve or reopen decisions), and the code areas it
  touches, and returns a verdict. The orchestrator fetches each issue's body and comments
  (`gh issue view N --json title,body,labels,comments`) and passes them in the judge prompt. The judge edits nothing and
  does not touch GitHub.

**Process.**
- *Phase 0, preflight.* `gh repo view` (fail if no repo / not authenticated). Parse arguments.
  Ensure the label exists by running `gh label create <label>` and treating an "already exists"
  error as success (`gh label list` returns only 30 labels) (skipped on dry run).
- *Phase 1, candidates.* `gh issue list --state open --json number,title,labels,assignees,createdAt,closedByPullRequestsReferences,blockedBy,subIssuesSummary`
  with a high `--limit` (all open issues). Drop, without a judge: issues already carrying the label (unless
  `recheck`), and issues that are assigned or have an open linked PR (someone is on
  it). The **native dependency data** comes from the same list call (`blockedBy`, `subIssuesSummary`); no per-issue calls.
  An issue with an open native blocker or open sub-issues is dropped here without a judge and
  reported as not-ready/`dependency` or as a tracking issue. The rest are sorted oldest first and
  capped at `limit`; the remainder is reported as "over limit".
- *Phase 2, judging.* Each judge gets the issue number, title, labels, body and comments, and the rubric below, and replies
  with a fixed record: `number`, `verdict` (`ready`/`not-ready`), `reason` (`ux` | `dependency` |
  `high-risk` | `underspecified` | `other`), `why` (one sentence), `blockers` (issue numbers the text says this
  depends on, including prose like "after #12", "needs #7", "once X lands"), and for `ready` a
  `decisions-covered` line naming the non-obvious decisions the issue already settles. The record
  format is stated once, in the skill's judge prompt.
- *Phase 3, dependency check.* The orchestrator runs `gh issue view` on each judge-reported blocker;
  any still open flips the verdict to `not-ready` / `dependency`. Verdicts
  are never flipped the other way. Prose blockers that name no issue number (e.g. "once the API
  lands") are the judge's to weigh: it must treat an unresolved, unnamed prerequisite as `dependency`.
- *Phase 4, apply.* `gh issue edit N --add-label <label>` for each `ready`. With `recheck`, a
  previously labeled issue that is now `not-ready` gets the label removed (`--remove-label`) and the
  reason reported. Dry run prints what would change.
- *Phase 5, report.* A table: ready (labeled), not-ready grouped by reason with the one-line why,
  skipped (assigned, linked PR, tracking issue, over limit), and removals. Not-ready lines are the
  user's feedback on how to make an issue bot-ready.

**Judge rubric** (the skill's core content; "conservative bot" is the test: a bot that will not ask
questions and will pick the most conservative option when unsure, so it needs the decisions that
matter to be already made).
1. *UX component → out.* Anything whose acceptance depends on how it looks, reads, or feels to a
   person: new/changed screens, layout, styling, interaction flow, copy/wording shown to users,
   accessibility behavior, onboarding, or an issue labeled/mentioning design, UX, UI, or mockups.
   Ambiguous → out. Pure backend, API, CLI-logic, infra, refactor, or test work is not UX.
2. *Unmet dependency → out.* Blocked by an open issue/PR, waits on an external service, release,
   credential, or decision by a named person, or presupposes code that does not exist yet.
3. *High risk → out.* A silent or hard-to-reverse failure in the change would be costly, however
   well specified: authentication/authorization/permissions, secrets and credentials, security
   fixes, money/billing/payments, database or data migrations, destructive or bulk data changes,
   concurrency/locking, and release, deploy, or CI/infra changes that affect production. A change
   merely adjacent to such code (a typo in a comment, a test for it) is not high risk; if the
   change itself alters its behavior, it is. Ambiguous → out.
4. *Sufficiently specified → required to be ready.* All of: the desired end state is stated; scope
   is bounded (one change a single PR can hold); success is checkable (acceptance criteria, a repro,
   or an expected output); the code area is locatable (named, or obvious from a quick search); and
   no unresolved choice that needs a product or architecture opinion (approach options listed
   without a pick, "should we…?", "discuss", "RFC", open questions in comments). A choice the
   codebase's existing patterns settle does not count as unresolved. A bug report must be
   reproducible from the description.
5. When in doubt, `not-ready`. A missed ready issue costs one more triage; a wrongly labeled one
   costs a bot's wasted run and a bad PR.

## Implementation Steps
1. Create `skills/triage-issues/SKILL.md`: frontmatter (`name: triage-issues`, `description`,
   `argument-hint`, `allowed-tools: Bash(gh issue list *), Bash(gh issue view *), Bash(gh issue edit *), Bash(gh label *), Bash(gh repo view *), Read, Task`), the canonical Model tiers paragraph copied
   byte-for-byte from another carrier (e.g. `babysit-pr`), then Roles, Process (phases above),
   judge prompt with rubric and record format, and Notes (stating dependency data comes from `gh issue list --json`, so no `gh api`).
2. `README.md`: add a `/triage-issues` row to the skill table, positioned before `/ship-issue`, and
   a sentence that it prepares issues for `/ship-auto`; update any skill count in prose.
3. `CLAUDE.md`: "thirteen" → "fourteen" slash-command skills and add `/triage-issues` to the list;
   add the architecture-tree line for `triage-issues/SKILL.md`; in the Model-tier convention bullet
   change "all seven carriers" to the new carrier count (eight).
4. `CHANGELOG.md`: new `## [1.33.0] - 2026-11-14` entry; bump `.claude-plugin/plugin.json` version
   to `1.33.0`.
5. Run `python3 scripts/validate.py` and `python3 scripts/test_validate.py`.

## Files to Modify
- `skills/triage-issues/SKILL.md` (new)
- `README.md`
- `CLAUDE.md`
- `CHANGELOG.md`
- `.claude-plugin/plugin.json`

## Trade-offs
- **One judge per issue vs. one agent for the whole backlog.** Per-issue costs more tokens but
  gives independent, uncontaminated verdicts and lets the 5-wide batches run concurrently; a single
  agent drifts toward consistency with its own earlier calls. `limit` bounds the cost.
- **Label only vs. also commenting the reason on the issue.** Comments would spam issues and
  notify watchers; the reasons live in the run report instead.
- **Orchestrator verifies dependency state vs. trusting the judge.** The open/closed state of an
  issue is a fact, not a judgment, so it is fetched, not inferred.
- **Reuse `ship-issue`'s own checks instead of a new skill.** Rejected: `ship-issue` runs after
  commitment to one issue; triage runs across the backlog before any commitment.

## Decisions
- Default label `bot-ready`, overridable per run, so the skill fits repos with their own naming.
- Never removes a label unless `recheck` is given, since humans may have applied it by hand.
- High-risk issues are never `bot-ready`, however well specified (user call). Their category list is
  the rubric's, stated once there.

## Documentation
README skill table and prose; CLAUDE.md skill list, architecture tree, and tier-carrier count;
CHANGELOG.

## Testing Strategy
There is no pure logic to unit test: the skill is prompt text, and the verdict is an LLM judgment.
Automated coverage is the existing `scripts/validate.py` (frontmatter, tier declaration, README and
CLAUDE.md coverage, `Task` declared in `allowed-tools`) and `scripts/test_validate.py`, both of
which already run in CI and must pass with the new skill.

## Manual Verification
Judgment quality cannot be unit tested, and a bad verdict is visible in the report, not silent
(labeling is reversible and `dry run` exists).
1. In a scratch repo with a handful of issues (one clear backend bug with repro, one UI change, one
   blocked by an open issue via "blocked by #N", one well-specified DB migration, one vague
   "improve performance"), run
   `/dev-skills:triage-issues — dry run`. Expected: only the backend bug is `ready`; the others
   show reasons `ux`, `dependency`, `high-risk`, `underspecified`; no labels changed.
2. Run `/dev-skills:triage-issues`. Expected: the label is created if missing and `gh issue list --label bot-ready` shows
   exactly the ready issue.
3. Close the blocker, run again without `recheck`. Expected: the dependency-blocked issue is now
   assessed on its merits; if it is `not-ready` for another reason the report says so.

