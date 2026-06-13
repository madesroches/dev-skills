---
name: branch-review-loop
description: Iteratively review and fix the current branch until it converges (no substantive issues remain)
argument-hint: "[base-branch]"
allowed-tools: Read, Write, Bash(git *), Bash(echo *), Bash(dirname *), Task
---

# Branch Review Loop — Review → Fix → Repeat Until Clean

Iteratively harden the current branch against `$ARGUMENTS` (default: `main`). Each round, a
**fresh** reviewer agent runs the `branch-review` process against the branch's *current* diff,
then a fixer agent applies the confirmed fixes in the code. The loop ends when a round surfaces
no substantive issues, when the work stops converging, or when a round cap is hit.

This skill is **fully autonomous** once started — it does not prompt between rounds. It commits
the fixes after each fixer pass so every round is diffable and revertable.

## Why a loop with fresh agents

A single review only catches the issues visible in the branch's *current* diff. Fixing those
issues changes the code and can expose or introduce new problems. Re-reviewing catches them —
but only if the reviewer starts cold.

**The reviewer must begin from a blank context every round.** If it carried over the previous
round's findings, it would anchor on already-fixed issues and miss what the edits newly exposed.
Spawning a brand-new `Task` agent each round guarantees this: the agent sees only the diff as it
stands now, with no memory of prior rounds. The orchestrator (this skill) keeps the cross-round
bookkeeping; the reviewer never sees it.

## Roles

- **Orchestrator** — this skill, running in the main context. Drives the loop, tracks per-round
  findings to detect non-convergence, commits after each fix, and writes the final summary. It
  does **not** review or edit code itself.
- **Reviewer agent** — a fresh `Task` agent (`subagent_type: "general-purpose"`) spawned each
  round. Runs `branch-review` Phases 1–4 only and returns a structured issue list.
- **Fixer agent** — a `Task` agent (`subagent_type: "general-purpose"`) spawned each round that
  has substantive issues. Edits the code to resolve them and reports what it changed.

## Process

### Phase 0: Preflight

1. Resolve the base branch from `$ARGUMENTS` (default `main`). Confirm it exists
   (`git rev-parse --verify <base>`); if not, ask the user and stop.
2. Confirm there is a diff to review (`git diff <base>..HEAD --stat`). If empty, report and stop.
3. The fixer commits code each round, so the working tree must be clean. Run `git status --short`.
   If there are uncommitted changes, commit them first so round commits are isolated (do not stash —
   the reviewer reviews committed state). Run as two separate calls: `git add -A`, then
   `git commit -m "branch-review-loop: baseline"`. (A fixed string like this is safe inline; the
   meaningful per-round messages in Phase 4 are not — see there.)
4. Resolve the absolute path to the companion `branch-review` skill. The reviewer runs as a
   subagent, which cannot use the Skill tool and does not share this skill's working directory,
   so it must be given an absolute filesystem path:
   !`echo "$(dirname "$CLAUDE_SKILL_DIR")/branch-review/SKILL.md"`
   Use this absolute path wherever the reviewer prompt below says `<review skill path>`.
5. Initialize round counter `N = 0` and an empty `history` of substantive issue summaries per round.

Set a round cap of **5** unless the user specified otherwise in `$ARGUMENTS`.

### Phase 1: Review (fresh agent)

Increment `N`. Spawn a **new** reviewer agent. Its prompt must contain **only** the base branch
and the instructions below — never the findings or context from previous rounds.

> Run the `branch-review` skill's process (Phases 1–4) on the current branch against base `<base>`.
> Read the review process from the file at `<review skill path>` and follow it exactly for Phases
> 1–4: gather the diff, identify candidate issues, verify them in parallel with `Explore` agents,
> and confirm which are real.
>
> **Do not run Phase 5** — do not ask the user anything and do not edit any code.
>
> Return confirmed issues only, as a list. For each confirmed issue provide:
> - `severity`: `substantive` (a real bug, logic/race/security/type error, breakage, or missing
>   handling that should be fixed) or `trivial` (style, naming, formatting, optional polish, or nitpick)
> - `summary`: one line
> - `location`: file and line reference
> - `why`: what you verified that makes it a real problem
> - `fix`: the suggested fix in one sentence
>
> If there are no confirmed issues, return exactly `NO ISSUES`.

Collect the reviewer's structured result.

### Phase 2: Decide whether to continue

Partition the confirmed issues into `substantive` and `trivial`.

Stop the loop and go to **Phase 5** if any of these hold:

- **Clean:** there are no confirmed issues (`NO ISSUES`).
- **Only trivial remain:** there are zero substantive issues. Trivial issues are reported, not
  fixed — fixing them round after round invites churn and they are not worth a loop.
- **Round cap:** `N` has reached the cap (default 5).
- **Non-convergence:** the set of substantive issues this round is essentially the same as a
  previous round's (compare against `history` by summary/location). This means the fixer failed to
  resolve them or keeps reintroducing them — looping again will not help.
- **Oscillation:** issue counts are not trending down across rounds (e.g. round N has as many or
  more substantive issues than round N-1, and they are not net-new follow-ons from a fix).

Otherwise, record this round's substantive issue summaries in `history` and continue to Phase 3.

### Phase 3: Fix (per-round agent)

Before spawning the fixer, print a summary of the substantive issues about to be fixed. Format it
as a short numbered list — one line per issue: `file: summary → fix`. Label it clearly, e.g.
`Round N — fixing X issue(s):`. This gives the user visibility into what is being changed before
any edits happen.

Spawn a fixer agent with: the base branch and the **substantive** issues from this round (summary,
location, why, fix for each). Instruct it to:

> For each issue, edit the code to resolve it. Apply the suggested fix or a better one if the
> suggestion is wrong. Keep edits minimal and localized — change only what the issue requires; do
> not refactor unrelated code or introduce new scope. If the project has fast, relevant checks
> (lint/tests for the touched files), run them to confirm your edits don't break the build. When
> done, return a one-line description of each edit you made and the file you touched.

Trivial issues from this round are **not** sent to the fixer. They are accumulated for the final summary.

### Phase 4: Commit and loop

After the fixer returns, commit the fixes with a **meaningful message** that describes what was
actually fixed — not a generic round label. Build it from the fixer's reported edits:

1. Compose the commit message:
   - **Subject** (≤ 72 chars): a concise summary of the round's fixes, e.g.
     `Guard nil session in auth handler; fix off-by-one in pager`. If the round had many fixes,
     summarize the theme rather than cramming each into the subject.
   - **Body**: one bullet per edit the fixer reported (its one-line descriptions), so the diff is
     self-documenting.
2. Write that message to `/tmp/REVIEW_LOOP_COMMIT_MSG` using the **Write** tool. Do **not** pass the
   message inline with `git commit -m`: a meaningful message contains quotes, backticks, and other
   shell metacharacters that the command-safety checker flags, which would stall this autonomous
   loop on a permission prompt. Writing to a file and committing with `-F` keeps the bash command
   free of any message text. Use `/tmp/REVIEW_LOOP_COMMIT_MSG` (absolute path) — the Write tool
   requires absolute paths.
3. Stage only the files the fixer changed, by explicit path: `git add <file> [<file> ...]`. Avoid
   `git add -A` so unrelated working-tree changes never sneak into the round commit.
4. Commit: `git commit -F /tmp/REVIEW_LOOP_COMMIT_MSG`.
5. Record the new commit's short SHA and subject for the final summary, then return to **Phase 1**
   with a fresh reviewer agent.

Run `git add` and `git commit` as **separate** Bash calls — never chained with `&&`. Each is then a
plain `git …` invocation that matches the `Bash(git *)` allowlist and clears the checker without a
prompt.

### Phase 5: Final summary

When the loop ends, output a concise report:

- **Outcome** — which stopping condition fired (clean / only trivial / round cap / non-convergence / oscillation).
- **Rounds run** — `N`, with a one-line note per round on what was found and fixed.
- **Remaining issues** — any trivial issues from the last review, and (if the loop stopped on cap or
  non-convergence) the unresolved substantive issues, so the user can decide what to do next.
- **Commits** — the per-round fix commits created (short SHA + subject line), so the user can
  review or revert the diff.

Do not prompt the user during the loop. If the loop stopped on non-convergence or the round cap with
substantive issues outstanding, say so plainly and hand control back — do not keep looping.

## Notes

- Keep the reviewer's prompt free of prior-round context. This is the one invariant that makes the
  loop work; if you ever find yourself summarizing earlier findings into the reviewer prompt, stop.
- The orchestrator never edits code or runs the review itself — delegating both keeps its own context
  from accumulating round-over-round bias and keeps roles auditable via the per-round commits.
- This skill builds directly on `branch-review`; if that skill's process changes, this loop inherits
  the change because the reviewer agent is told to follow the `branch-review` SKILL.md at its
  resolved absolute path (`<review skill path>`).
