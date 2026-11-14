---
name: triage-issues
description: Scan a project's open GitHub issues and label the ones a conservative implementation bot can complete without guessing
argument-hint: "[— label NAME] [— limit N] [— recheck] [— dry run]"
allowed-tools: Bash(gh issue list *), Bash(gh issue view *), Bash(gh issue edit *), Bash(gh label *), Bash(gh repo view *), Bash(gh api repos/*), Read, Task
---

# Triage Issues — Label What a Bot Can Ship

Scan the open issues of the current GitHub repository and apply a `bot-ready` label to the ones a
conservative implementation bot (`/dev-skills:ship-issue`, `/dev-skills:ship-auto`) has a good chance of
completing without guessing. Each issue is judged by a `{{thinking}}` agent. An issue is ruled out if
it has a UX component, has an unmet dependency, is high-risk, or is not described well enough for the
bot to settle every decision it will face.

**Model tiers.** This skill names models by role. `{{coding}}` is the tier for well-specified,
mechanical work — pass `model: "sonnet"`. `{{thinking}}` is the tier for judgment — pass
`model: "opus"`. To run on other models, remap those aliases with Claude Code's
`ANTHROPIC_DEFAULT_SONNET_MODEL` / `ANTHROPIC_DEFAULT_OPUS_MODEL`, or swap the two quoted
values for another alias (`sonnet`, `opus`, `haiku`, `fable`) here.

This skill is **fully autonomous** — it does not prompt. It only ever adds the label, except with
`recheck` (below). It never comments on issues.

## Arguments

Parsed from `$ARGUMENTS`:
- `label NAME` — the label to apply, default `bot-ready`.
- `limit N` — max issues judged per run, default 30 (each costs a `{{thinking}}` agent); applied after
  filtering, oldest first.
- `recheck` — also re-assess issues that already carry the label.
- `dry run` — report verdicts, change nothing on GitHub.

## Roles

- **Orchestrator** — this skill, in the main context. Lists issues, gathers mechanical facts,
  dispatches judges, applies labels, and writes the report. It does **not** judge issues itself.
- **Judge agent** — one fresh `Task` agent per issue (`subagent_type: "general-purpose"`,
  `model` = `{{thinking}}`), run in parallel batches of 5. One agent per issue keeps verdicts
  independent. It reads the issue, **all** its comments (they often resolve or reopen decisions), and
  the code areas the issue touches, and returns a verdict. It edits nothing and does not touch GitHub.

## Process

### Phase 0: Preflight

1. `gh repo view --json nameWithOwner`. If there is no repo or `gh` is not authenticated, say so and stop.
2. Parse the arguments (above).
3. Ensure the label exists: run `gh label create <label>` and treat an "already exists" error as success (do not rely on `gh label list`, which returns only 30 labels by default)
   (skipped on dry run).

### Phase 1: Candidates

1. `gh issue list --state open --json number,title,labels,assignees,createdAt,closedByPullRequestsReferences`
   with a high `--limit` (all open issues).
2. Drop, without a judge: issues already carrying the label (unless `recheck`), pull requests, and
   issues that are assigned or have an open linked PR (someone is on it).
3. For each remaining issue, pre-fetch the **native dependency data**:
   `gh api repos/{owner}/{repo}/issues/N/dependencies/blocked_by` and
   `gh api repos/{owner}/{repo}/issues/N/sub_issues`. An issue with an open native blocker is dropped
   here without a judge and reported as not-ready / `dependency`; one with open sub-issues is dropped
   and reported as a tracking issue.
4. Sort the rest oldest first and cap at `limit`; report the remainder as "over limit".

### Phase 2: Judging

For each candidate, fetch `gh issue view N --comments` and spawn a judge (batches of 5 in parallel)
with the issue number, the issue body and all comments, and the prompt below. Judges reply with the
record defined in the prompt.

**Judge prompt.** Pass this to each judge, filling in the issue:

> You are judging whether GitHub issue #N can be completed by a conservative implementation bot. The
> bot will not ask questions and will pick the most conservative option when unsure, so the decisions
> that matter must already be made. Read the issue and every comment below, then search the codebase
> for the areas it touches. Edit nothing; do not touch GitHub.
>
> 1. **UX component → out.** Anything whose acceptance depends on how it looks, reads, or feels to a
>    person: new/changed screens, layout, styling, interaction flow, copy/wording shown to users,
>    accessibility behavior, onboarding, or an issue labeled/mentioning design, UX, UI, or mockups.
>    Ambiguous → out. Pure backend, API, CLI-logic, infra, refactor, or test work is not UX.
> 2. **Unmet dependency → out.** Blocked by an open issue/PR, waits on an external service, release,
>    credential, or decision by a named person, or presupposes code that does not exist yet. Treat an
>    unresolved, unnamed prerequisite ("once the API lands") as `dependency`.
> 3. **High risk → out.** A silent or hard-to-reverse failure in the change would be costly, however
>    well specified: authentication/authorization/permissions, secrets and credentials, security
>    fixes, money/billing/payments, database or data migrations, destructive or bulk data changes,
>    concurrency/locking, and release, deploy, or CI/infra changes that affect production. A change
>    merely adjacent to such code (a typo in a comment, a test for it) is not high risk; if the change
>    itself alters its behavior, it is. Ambiguous → out.
> 4. **Sufficiently specified → required to be ready.** All of: the desired end state is stated; scope
>    is bounded (one change a single PR can hold); success is checkable (acceptance criteria, a repro,
>    or an expected output); the code area is locatable (named, or obvious from a quick search); and
>    no unresolved choice that needs a product or architecture opinion (approach options listed
>    without a pick, "should we…?", "discuss", "RFC", open questions in comments). A choice the
>    codebase's existing patterns settle does not count as unresolved. A bug report must be
>    reproducible from the description.
> 5. **When in doubt, `not-ready`.** A missed ready issue costs one more triage; a wrongly labeled one
>    costs a bot's wasted run and a bad PR.
>
> Reply with exactly this record:
> - `number`: the issue number
> - `verdict`: `ready` or `not-ready`
> - `reason`: `ux` | `dependency` | `high-risk` | `underspecified` | `other` (for `ready`, `none`)
> - `why`: one sentence
> - `blockers`: issue numbers the text says this depends on, including prose like "after #12",
>   "needs #7", "once X lands" (or `none`)
> - `decisions-covered`: for `ready`, the non-obvious decisions the issue already settles

### Phase 3: Dependency check

Run `gh issue view <n> --json state` on each judge-reported blocker; any still open flips that
issue's verdict to `not-ready` / `dependency`. Verdicts are never flipped the other way.

### Phase 4: Apply

- `gh issue edit N --add-label <label>` for each `ready`.
- With `recheck`, a previously labeled issue that is now `not-ready` gets the label removed
  (`gh issue edit N --remove-label <label>`) and the reason reported.
- On dry run, print what would change and change nothing.

### Phase 5: Report

A table: **ready** (labeled), **not-ready** grouped by reason with the one-line why, **skipped**
(assigned, linked PR, tracking issue, over limit), and **removals**. The not-ready lines are the
user's feedback on how to make an issue bot-ready.

## Notes

- **One judge per issue.** Costs more tokens than a single agent over the whole backlog, but verdicts
  stay independent and run concurrently; `limit` bounds the cost.
- **Label only, no comments.** Comments would spam issues and notify watchers; the reasons live in
  the run report.
- **Facts are fetched, not inferred.** Whether a blocker is open or closed is checked by the
  orchestrator, never trusted from the judge.
- **Never removes a label without `recheck`**, since humans may have applied it by hand.
- **`gh api` is GET-only** here: dependency and sub-issue lookups, never a mutation.
- **High-risk issues are never labeled**, however well specified.
