---
name: design-review-loop
description: Iteratively review and fix a design plan until it converges (no substantive issues remain)
argument-hint: "<path to plan file>"
allowed-tools: Read, Bash(git *), Task
---

# Design Review Loop — Review → Fix → Repeat Until Clean

Iteratively harden the design plan at `$ARGUMENTS`. Each round, a **fresh** reviewer
agent runs the `design-review` process against the plan's *current* state, then a fixer
agent applies the confirmed fixes. The loop ends when a round surfaces no substantive
issues, when the work stops converging, or when a round cap is hit.

This skill is **fully autonomous** once started — it does not prompt between rounds. It
commits the plan file after each fixer pass so every round is diffable and revertable.

## Why a loop with fresh agents

A single review only catches the issues visible in the plan's *original* state. Fixing
those issues changes the plan and can expose or introduce new problems. Re-reviewing
catches them — but only if the reviewer starts cold.

**The reviewer must begin from a blank context every round.** If it carried over the
previous round's findings, it would anchor on already-fixed issues and miss what the
edits newly exposed. Spawning a brand-new `Task` agent each round guarantees this: the
agent sees only the plan file as it stands now, with no memory of prior rounds. The
orchestrator (this skill) keeps the cross-round bookkeeping; the reviewer never sees it.

## Roles

- **Orchestrator** — this skill, running in the main context. Drives the loop, tracks
  per-round findings to detect non-convergence, commits after each fix, and writes the
  final summary. It does **not** review or edit the plan itself.
- **Reviewer agent** — a fresh `Task` agent (`subagent_type: "general-purpose"`) spawned
  each round. Runs `design-review` Phases 1–4 only and returns a structured issue list.
- **Fixer agent** — a `Task` agent (`subagent_type: "general-purpose"`) spawned each round
  that has substantive issues. Edits the plan file to resolve them and reports what it changed.

## Process

### Phase 0: Preflight

1. Confirm `$ARGUMENTS` points to an existing plan file. If missing, ask the user for the path and stop.
2. Confirm the working tree is clean enough to commit the plan file per round
   (`git status --short -- <plan file>`). If the plan file already has uncommitted changes,
   commit them first as `design-review-loop: baseline` so round commits are isolated.
3. Initialize round counter `N = 0` and an empty `history` of substantive issue summaries per round.

Set a round cap of **5** unless the user specified otherwise in `$ARGUMENTS`.

### Phase 1: Review (fresh agent)

Increment `N`. Spawn a **new** reviewer agent. Its prompt must contain **only** the plan
path and the instructions below — never the findings or context from previous rounds.

> Run the `design-review` skill's process (Phases 1–4) on the plan file at `<plan path>`.
> Follow `skills/design-review/SKILL.md` exactly for Phases 1–4: gather context, identify
> candidate issues, verify them in parallel with `Explore` agents, and confirm which are real.
>
> **Do not run Phase 5** — do not ask the user anything and do not edit the plan.
>
> Return confirmed issues only, as a list. For each confirmed issue provide:
> - `severity`: `substantive` (a real design flaw, ambiguity, or correctness/ordering/breakage problem
>   that should be fixed) or `trivial` (wording, formatting, optional polish, or nitpick)
> - `summary`: one line
> - `section`: which plan section is involved
> - `why`: what you verified against the code that makes it a real problem
> - `fix`: the suggested fix in one sentence
>
> If there are no confirmed issues, return exactly `NO ISSUES`.

Collect the reviewer's structured result.

### Phase 2: Decide whether to continue

Partition the confirmed issues into `substantive` and `trivial`.

Stop the loop and go to **Phase 5** if any of these hold:

- **Clean:** there are no confirmed issues (`NO ISSUES`).
- **Only trivial remain:** there are zero substantive issues. Trivial issues are reported,
  not fixed — fixing them round after round invites churn and they are not worth a loop.
- **Round cap:** `N` has reached the cap (default 5).
- **Non-convergence:** the set of substantive issues this round is essentially the same as a
  previous round's (compare against `history` by summary/section). This means the fixer failed
  to resolve them or keeps reintroducing them — looping again will not help.
- **Oscillation:** issue counts are not trending down across rounds (e.g. round N has as many
  or more substantive issues than round N-1, and they are not net-new follow-ons from a fix).

Otherwise, record this round's substantive issue summaries in `history` and continue to Phase 3.

### Phase 3: Fix (per-round agent)

Spawn a fixer agent with: the plan path and the **substantive** issues from this round
(summary, section, why, fix for each). Instruct it to:

> For each issue, edit the plan file at `<plan path>` to resolve it. Apply the suggested fix
> or a better one if the suggestion is wrong. Keep edits minimal and localized — change only
> what the issue requires; do not rewrite unrelated sections. Do not introduce new scope.
> When done, return a one-line description of each edit you made and the section you touched.

Trivial issues from this round are **not** sent to the fixer. They are accumulated for the
final summary.

### Phase 4: Commit and loop

After the fixer returns:

1. Commit the plan file: `git add <plan file> && git commit -m "design-review-loop: round <N> fixes"`.
   Commit the plan file only — do not stage unrelated changes.
2. Return to **Phase 1** with a fresh reviewer agent.

### Phase 5: Final summary

When the loop ends, output a concise report:

- **Outcome** — which stopping condition fired (clean / only trivial / round cap / non-convergence / oscillation).
- **Rounds run** — `N`, with a one-line note per round on what was found and fixed.
- **Remaining issues** — any trivial issues from the last review, and (if the loop stopped on cap
  or non-convergence) the unresolved substantive issues, so the user can decide what to do next.
- **Commits** — the list of `design-review-loop: round N fixes` commits created, so the user can
  review or revert the diff.

Do not prompt the user during the loop. If the loop stopped on non-convergence or the round cap
with substantive issues outstanding, say so plainly and hand control back — do not keep looping.

## Notes

- Keep the reviewer's prompt free of prior-round context. This is the one invariant that makes the
  loop work; if you ever find yourself summarizing earlier findings into the reviewer prompt, stop.
- The orchestrator never edits the plan or runs the review itself — delegating both keeps its own
  context from accumulating round-over-round bias and keeps roles auditable via the per-round commits.
- This skill builds directly on `design-review`; if that skill's process changes, this loop inherits
  the change because the reviewer agent is told to follow `skills/design-review/SKILL.md`.
