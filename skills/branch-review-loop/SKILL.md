---
name: branch-review-loop
description: Iteratively review and fix the current branch until it converges (no substantive issues remain)
argument-hint: "[base-branch]"
allowed-tools: Read, Write, Bash(git *), Bash(echo *), Bash(dirname *), Bash(mktemp *), Task, AskUserQuestion
---

# Branch Review Loop — Review → Fix → Repeat Until Clean

Iteratively harden the current branch against `$ARGUMENTS` (default: the repo's default
branch — see Phase 0). Each round, a
**fresh** reviewer agent runs the `branch-review` process against the branch's *current* diff,
then a fixer agent applies the confirmed fixes in the code. The loop ends when a round surfaces
no substantive issues, when the work stops converging, or when a round cap is hit. A final pass
then clears whatever the loop left behind — the trivial issues it deliberately skipped each round,
plus any substantive issues still open — so the branch is handed back with no known open issues.

This skill is **fully autonomous** once started — it does not prompt between rounds. It commits
the fixes after each fixer pass so every round is diffable and revertable.

## Why a loop with fresh agents

A single review only catches the issues visible in the branch's *current* diff. Fixing those
issues changes the code and can expose or introduce new problems. Re-reviewing catches them —
but only if the reviewer starts cold.

**The reviewer must begin from a blank context every round.** If it carried over the previous
round's findings, it would anchor on already-fixed issues and miss what the edits newly exposed.
Spawning a brand-new `Task` agent each round guarantees this: the agent sees only the diff as it
stands now — plus the branch's plan file, if one exists, for recorded verification decisions —
with no memory of prior rounds' findings. The orchestrator (this skill) keeps the cross-round
bookkeeping; the reviewer never sees it.

## Roles

- **Orchestrator** — this skill, running in the main context. Drives the loop, tracks per-round
  findings to detect non-convergence, commits after each fix, and writes the final summary. It
  does **not** review or edit code itself.
- **Reviewer agent** — a fresh `Task` agent (`subagent_type: "general-purpose"`) spawned each
  round. Runs `branch-review` Phases 1–4 only and returns a structured issue list. By default uses
  whatever model the user currently has set — no override — since review quality should track the
  user's own model choice, not a fixed tier. A caller can explicitly request a different model for
  the reviewer (see Phase 0); this is the mechanism `implement-and-review` and `ship-issue` use to
  get an `opus` reviewer without restating this skill's process.
- **Fixer agent** — a `Task` agent (`subagent_type: "general-purpose"`, `model: "sonnet"`) spawned
  each round that has substantive issues. Edits the code to resolve them and reports what it
  changed. Fixing a confirmed, well-specified issue is comparatively mechanical, so `sonnet` is
  sufficient and keeps the loop cheaper.
- **Finalize agent** — a `Task` agent (`subagent_type: "general-purpose"`, `model: "sonnet"`)
  spawned at most once, after the loop ends, only if anything is left unresolved. Fixes the
  leftovers in one pass. Unlike the per-round fixer, its work is **not** re-reviewed — the point is
  to close out known issues, not to restart the loop.

## Process

### Phase 0: Preflight

1. Resolve the base branch from `$ARGUMENTS`; if none is given, use the repo's default branch
   (`git symbolic-ref --short refs/remotes/origin/HEAD`, stripping the `origin/` prefix; fall
   back to `main` if no remote HEAD is configured). Confirm it exists
   (`git rev-parse --verify <base>`); if not, ask the user and stop.
2. Confirm there is a diff to review (`git diff <base>...HEAD --stat` — three-dot, matching how
   `branch-review` diffs from the merge-base). If empty, report and stop.
3. The fixer commits code each round, so the working tree must be clean. Run `git status --short`.
   If there are uncommitted changes, show that output to the user and ask with AskUserQuestion
   whether to commit them as a baseline or stop — they may be unrelated WIP the user does not
   want swept into this loop's history. (This is preflight; the no-prompting rule only applies
   once the loop is running.) If they choose to stop, stop. If they choose to commit (do not
   stash — the reviewer reviews committed state): stage by explicit path from the
   `git status --short` output — tracked and untracked alike — never `git add -A`, so nothing
   sweeps in silently. Run as two separate calls: `git add <file> [<file> ...]`, then
   `git commit -m "branch-review-loop: baseline"`. (A fixed string like this is safe inline; the
   meaningful per-round messages in Phase 4 are not — see there.)
4. Resolve the absolute path to the companion `branch-review` skill. The reviewer runs as a
   subagent, which cannot use the Skill tool and does not share this skill's working directory,
   so it must be given an absolute filesystem path:
   !`echo "$(dirname "$CLAUDE_SKILL_DIR")/branch-review/SKILL.md"`
   Use this absolute path wherever the reviewer prompt below says `<review skill path>`.
5. Generate a unique path for the round commit-message scratch file. The Write tool requires an
   absolute path, but a fixed name under `/tmp` collides if the user runs this loop on another
   branch or worktree at the same time — so mint one per invocation:
   !`mktemp -u /tmp/branch-review-loop-commit-msg.XXXXXX`
   Use this exact path as `<commit msg path>` everywhere Phases 4 and 5 below reference it —
   each commit overwrites it, which is fine since commits are made one at a time.
6. Initialize round counter `N = 0`, an empty `history` of substantive issue summaries per round,
   and an empty `deferred` record of trivial issue summaries per round.

Set a round cap of **5** by default. If the user asked for a different cap, use that instead.

Set no reviewer model override by default — the reviewer inherits the session's current model.
If the invocation explicitly requests a different model for the reviewer (e.g. "use opus for the
reviewer"), use that model instead everywhere Phase 1 spawns the reviewer agent.

### Phase 1: Review (fresh agent)

Increment `N`. Spawn a **new** reviewer agent, using the reviewer model resolved in Phase 0 (no
override by default, so it inherits the user's current model; an explicitly requested override
otherwise). Its prompt must contain **only** the base branch and the instructions below — never
the findings or context from previous rounds.

> Run the `branch-review` skill's process (Phases 1–4) on the current branch against base `<base>`.
> Read the review process from the file at `<review skill path>` and follow it exactly for Phases
> 1–4: gather the diff, identify candidate issues, verify them in parallel with `Explore` agents,
> and confirm which are real.
>
> **Do not run that skill's Phase 5** — do not ask the user anything and do not edit any code.
>
> Return confirmed issues only, as a list, exactly in the structured format that skill's Phase 4
> defines — `severity`, `summary`, `location`, `why`, `fix` for each, with severity classified by
> that phase's definitions.
>
> If there are no confirmed issues, return exactly `NO ISSUES`.

Collect the reviewer's structured result.

### Phase 2: Decide whether to continue

Partition the confirmed issues into `substantive` and `trivial`.

Before applying the stop conditions, compare this round's issues against `deferred` (match by
summary/location, as for non-convergence). A re-report of a deferred trivial keeps its
**trivial** classification for the rest of this round, not just for the stop conditions below:
it is excluded from the substantive issues handed to this round's Phase 3 fixer, it is
re-appended to `deferred` with this round's other trivial issues, and — if this round turns out
to be the last one — it is counted among "its trivial issues" when Phase 5 gathers leftovers.
This holds regardless of the severity this round's fresh reviewer assigned — reclassification by
a reviewer who never saw the deferral is noise, not escalation.

Stop the loop and go to **Phase 5** if any of these hold:

- **Clean:** there are no confirmed issues (`NO ISSUES`).
- **Only trivial remain:** there are zero substantive issues. Trivial issues are not fixed
  *inside* the loop — fixing them round after round invites churn and they are not worth
  re-reviewing — they are cleared once at the end by the Phase 5 finalize pass.
- **Round cap:** `N` has reached the cap (default 5).
- **Non-convergence:** the set of substantive issues this round is essentially the same as a
  previous round's (compare against `history` by summary/location). This means the fixer failed to
  resolve them or keeps reintroducing them — looping again will not help.
- **Oscillation / accretion:** substantive counts have failed to decline for **two consecutive
  rounds** — whether or not the issues are net-new. One round of net-new follow-ons after a fix
  is normal; two is the signature of a loop manufacturing its own review surface, where each fix
  enlarges the diff and the enlargement is the next round's finding.

Otherwise, record this round's substantive issue summaries in `history`, append this round's
trivial issue summaries to `deferred`, and continue to Phase 3.

### Phase 3: Fix (per-round agent)

Before spawning the fixer, print a summary of the substantive issues about to be fixed. Format it
as a short numbered list — one line per issue: `file: summary → fix`. Label it clearly, e.g.
`Round N — fixing X issue(s):`. This gives the user visibility into what is being changed before
any edits happen.

Spawn a fixer agent with `model: "sonnet"`, passing: the base branch and the **substantive**
issues from this round (summary, location, why, fix for each). Instruct it to:

> For each issue, edit the code to resolve it. Apply the suggested fix or a better one if the
> suggestion is wrong. Keep edits minimal and localized — change only what the issue requires; do
> not refactor unrelated code or introduce new scope. When an issue's fix is a **deletion**,
> delete — do not soften it into a rewrite that keeps the text. If the project has fast, relevant
> checks (lint/tests for the touched files), run them to confirm your edits don't break the
> build. When done, return a one-line description of each edit you made and the file you touched.

Trivial issues from this round are **not** sent to the fixer — only the last round's trivial
issues matter, and they are handled once by the Phase 5 finalize pass.

### Phase 4: Commit and loop

After the fixer returns, commit the fixes with a **meaningful message** that describes what was
actually fixed — not a generic round label. Build it from the fixer's reported edits:

1. Compose the commit message:
   - **Subject** (≤ 72 chars): a concise summary of the round's fixes, e.g.
     `Guard nil session in auth handler; fix off-by-one in pager`. If the round had many fixes,
     summarize the theme rather than cramming each into the subject.
   - **Body**: one bullet per edit the fixer reported (its one-line descriptions), so the diff is
     self-documenting.
   - **No AI attribution** — no `Co-Authored-By` lines and no agent credit, in this and every
     other commit the loop makes (including the Phase 0 baseline).
2. Write that message to `<commit msg path>` (from Phase 0) using the **Write** tool. Do **not**
   pass the message inline with `git commit -m`: a meaningful message contains quotes, backticks,
   and other shell metacharacters that the command-safety checker flags, which would stall this
   autonomous loop on a permission prompt. Writing to a file and committing with `-F` keeps the
   bash command free of any message text.
3. Stage only the files the fixer changed, by explicit path: `git add <file> [<file> ...]`. Avoid
   `git add -A` so unrelated working-tree changes never sneak into the round commit.
4. Commit: `git commit -F <commit msg path>`.
5. Record the new commit's short SHA and subject for the final summary, then return to **Phase 1**
   with a fresh reviewer agent.

Run `git add` and `git commit` as **separate** Bash calls — never chained with `&&`. Each is then a
plain `git …` invocation that matches the `Bash(git *)` allowlist and clears the checker without a
prompt.

### Phase 5: Finalize — fix whatever the loop left behind

Gather everything the loop did not resolve, from the **last** review round only (earlier rounds'
issues were either fixed or re-reported by the next reviewer):

- Its trivial issues — never fixed inside the loop, by design.
- If the loop stopped on round cap, non-convergence, or oscillation/accretion: its unresolved
  substantive issues too — the newest crop of real findings, not the least consequential
  leftovers.

If there is nothing left (the loop stopped clean with zero confirmed issues), skip this phase
entirely — there is nothing to finalize or commit.

Otherwise, print the list of items about to be fixed — one line each: `file: summary` — labeled
e.g. `Finalizing X leftover issue(s):`. Then spawn one finalize agent with `model: "sonnet"`,
passing that list (summary, location, why, fix for each). Instruct it to:

> For each issue, edit the code to resolve it. Apply the suggested fix or a better one if the
> suggestion is wrong. Keep edits minimal and localized — change only what the issue requires; do
> not refactor unrelated code or introduce new scope. When an issue's fix is a **deletion**,
> delete rather than rewriting around the text. If any issue cannot be resolved without a
> decision you are not in a position to make, leave it alone and say so rather than guessing. If
> the project has fast, relevant checks (lint/tests for the touched files), run them to confirm
> your edits don't break the build. When done, return a one-line description of each edit you made
> and the file you touched, plus anything you deliberately left unfixed and why.

When it returns, commit its edits using the **same commit protocol as Phase 4** (compose a
meaningful message, write it to `<commit msg path>` with the Write tool, `git add` the changed
files by explicit path, `git commit -F <commit msg path>`, each git call separate, no AI
attribution). If the agent made no edits, make no commit.

Do **not** re-review after this pass and do **not** re-enter the loop — this is a single closing
pass. Anything the finalize agent reports as deliberately left unfixed goes into the Phase 6
summary rather than being silently dropped.

### Phase 6: Final summary

When the loop and the finalize pass are done, output a concise report:

- **Outcome** — which stopping condition ended the loop (clean / only trivial / round cap /
  non-convergence / oscillation-accretion).
- **Rounds run** — `N`, with a one-line note per round on what was found and fixed.
- **Finalize pass** — what it cleared, or that there was nothing left to finalize. If it was
  handed unresolved *substantive* issues (an accretion, cap, or non-convergence stop), say so
  plainly — those were real findings closed by an unreviewed pass.
- **Remaining issues** — anything the finalize agent left unfixed, so the user can decide what to
  do next.
- **Commits** — the per-round fix commits and the finalize commit (short SHA + subject line), so
  the user can review or revert the diff.

Do not prompt the user during the loop. If the loop stopped on non-convergence or the round cap with
substantive issues outstanding, say so plainly — the finalize pass takes one shot at them, and
whatever survives is reported, not looped on again.

## Notes

- Keep the reviewer's prompt free of prior-round context. This is the one invariant that makes the
  loop work; if you ever find yourself summarizing earlier findings into the reviewer prompt, stop.
- The orchestrator never edits code or runs the review itself — delegating both keeps its own context
  from accumulating round-over-round bias and keeps roles auditable via the per-round commits.
- The Phase 5 finalize pass is deliberately unreviewed. Re-reviewing it would restart the loop
  over changes that are usually the least consequential ones left — trivials the loop skipped. On
  a cap, non-convergence, or accretion stop that is *not* true: the pass gets the last round's
  unresolved substantive issues, which is why Phase 6 must name them explicitly rather than
  filing them under routine cleanup. Either way it runs, and whatever it introduces is the
  accepted cost of never handing back a branch with known open issues — callers get that
  guarantee from this skill and should not re-implement it.
- This skill builds directly on `branch-review`; if that skill's process changes, this loop inherits
  the change because the reviewer agent is told to follow the `branch-review` SKILL.md at its
  resolved absolute path (`<review skill path>`). The issue fields and severity definitions come
  from `branch-review` Phase 4's output contract, not from this skill.
- `branch-review-loop` and `design-review-loop` are deliberate near-mirrors. When changing shared
  loop mechanics here (preflight, stop conditions, commit protocol, reviewer/fixer roles, model
  overrides), make the same change in the sibling skill — history shows they drift otherwise.
- `design-review-loop` has two mechanics this skill **deliberately lacks**: a growth stop
  condition and the plan-size bookkeeping behind it. A plan's own bookkeeping turns every
  addition into a fresh consistency obligation a later reviewer finds violated, so plan review
  accretes; diff size is not the analogous signal for code, where fixes are checked by tests
  rather than by whether other sections re-enumerate them. The oscillation/accretion rule *is*
  shared.
