---
name: implement-and-review
description: Implement a design plan, commit it, then iteratively review and fix the branch with a stronger model until it converges
argument-hint: "<path to plan file>"
allowed-tools: Read, Write, Bash(git *), Bash(mktemp *), Task, AskUserQuestion, Skill
---

# Implement and Review — Build a Plan, Then Harden It

Implement the plan at `$ARGUMENTS`, commit the result, then run the `branch-review-loop`
process against the resulting branch to catch and fix anything the implementation missed.
The review loop's reviewer runs under `opus` regardless of the session's current model — this
skill exists specifically to pair fast implementation with a stronger, independent review pass.

The review loop closes out its own leftovers (its trivial issues and anything a non-clean stop
left open) in its final phase, so this skill does not add a cleanup pass of its own.

## Roles

- **Orchestrator** — this skill, running in the main context. Sequences implementation then
  review and writes the final summary. Does not write application code or review it itself.
- **Implementer agent** — a `Task` agent (`subagent_type: "general-purpose"`, `model: "sonnet"`)
  spawned once. Reads the plan, implements every step, and commits the result. `sonnet` is
  sufficient for well-specified implementation work coming from a plan document.
- **Review loop** — delegated directly to the `branch-review-loop` skill via the `Skill` tool,
  passing the base branch, a round cap of 10, and a request to use `opus` for the reviewer —
  parameters that skill's own Phase 0 already supports, so this is not a deviation from its
  process, just arguments it's designed to take. It also runs its own finalize pass at the end,
  clearing the trivial issues it skips each round and anything a non-clean stop left open. This
  skill automatically inherits any change to that loop's logic since nothing is restated.

## Process

### Phase 0: Preflight

1. Confirm `$ARGUMENTS` is provided and points to an existing file. Read it. If missing or
   not found, say so and stop — do not guess a plan.
2. Resolve the repo's base branch: `git symbolic-ref --short refs/remotes/origin/HEAD`,
   stripping the `origin/` prefix; if that fails (no remote HEAD configured), fall back to
   `main`. Use this as `<base>` here and in Phase 2.
3. `git status --short` — the implementer commits its own changes, so the tree should be
   clean first. If there are uncommitted changes, show that output to the user and ask with
   AskUserQuestion whether to commit them as a baseline or stop — they may be unrelated WIP the
   user does not want swept into this run's history. If they choose to stop, stop here, before
   touching any branch — nothing has been created or switched yet, so stopping leaves the tree
   exactly as found. If they choose to commit, or the tree is already clean, continue to the
   next step.
4. Check the current branch: `git branch --show-current`. If it is `<base>`, or empty (detached
   HEAD — `--show-current` prints nothing there, which would otherwise be mistaken for "already
   on a feature branch"), the implementer must not commit directly onto it — create a feature
   branch first, before any commit below or in later phases lands. Derive a short slug from the
   plan file's basename (lowercase, hyphens in place of spaces/underscores, extension stripped)
   and run `git checkout -b <slug>`. If the current branch is already something other than
   `<base>` and not detached, skip this — implement directly on it.
5. If step 3 called for a baseline commit, make it now, on top of the branch from step 4: stage
   by explicit path from the `git status --short` output — tracked and untracked alike — never
   `git add -A`, so nothing sweeps in silently. Run as two separate calls:
   `git add <file> [<file> ...]`, then `git commit -m "implement-and-review: baseline"`.
6. Generate a unique scratch path for the implementer's commit message (a fixed name under
   `/tmp` would collide across concurrent invocations):
   !`mktemp -u /tmp/implement-and-review-impl-commit-msg.XXXXXX`
   Use this exact path as `<impl commit msg path>`.

### Phase 1: Implement (sonnet agent)

Spawn one implementer agent with `model: "sonnet"`:

> Implement the plan at `<plan path>` in full. Read it carefully, then read whatever source
> files it references to confirm current state before editing. Follow the project's existing
> conventions (check `CLAUDE.md` if present). Implement every step in the plan — do not leave
> partial or stubbed work. If the project has fast, relevant checks (lint/tests for the
> touched areas), run them and fix any failures before committing.
>
> When implementation is complete:
> 1. Compose a commit message: a concise subject (≤ 72 chars) summarizing the change, and a
>    body with one bullet per notable change. Write it to `<impl commit msg path>` with the
>    Write tool — do not pass it inline with `git commit -m`, since it may contain quotes or
>    other shell metacharacters.
> 2. Stage only the files you changed, by explicit path (`git add <file> ...`) — never
>    `git add -A`.
> 3. Commit with `git commit -F <impl commit msg path>`.
> 4. **Do not add a `Co-Authored-By` line or any AI/agent attribution to the commit message or
>    author identity.** The commit must read as if written entirely by the repository's normal
>    author.
>
> Return: the commit SHA, a one-line description of what you implemented, and the results of
> any checks you ran.

If the agent reports it could not complete the plan (blocked, ambiguous, or failing checks it
couldn't resolve), stop here and report the blocker to the user instead of proceeding to review.

### Phase 2: Review loop (opus)

Confirm the implementer's commit landed (`git log --oneline -1`). Then invoke the
`branch-review-loop` skill via the `Skill` tool, passing: the base branch `<base>` (resolved in
this skill's Phase 0), an instruction to use a round cap of 10, and an instruction to use `opus`
for the reviewer (e.g. `<base> — use opus for the reviewer and a round cap of 10`). It runs its
whole process autonomously — including its own baseline-commit check, which will find nothing to
do since the tree is already clean after Phase 1's commit — committing after each fix round,
terminating on its own (clean / only trivial / round cap / non-convergence / oscillation-accretion), and
then running its own finalize pass over whatever it left unresolved.

Record which stopping condition ended the loop, plus what its finalize pass cleared and anything
it reported as still unfixed. Treat "clean" as **converged**; every other stopping condition
(including "only trivial", since that means substantive issues were resolved but something was
still left over for the finalize pass) as **did not fully converge** — be precise about which one
it actually was.

### Phase 3: Final summary

Report:
- The implementer's commit (SHA + one-line description) and any checks it ran.
- The review loop's outcome: rounds run, per-round fix commits, and the **convergence
  status** — state plainly whether it converged (stopped clean) or did not (hit the round cap,
  stopped with only trivial issues remaining, or stopped on non-convergence or
  oscillation/accretion with issues still outstanding at that point).
- Its finalize pass: the commit it made (SHA + what it fixed), or that nothing was left to
  finalize — and any issue it reported as deliberately left unfixed.

## Notes

- Keep the implementer and reviewer roles separate — the implementer never reviews its own
  work, and the reviewer never sees the plan, only the resulting diff. This mirrors why
  `branch-review-loop` always starts its reviewer from a blank context.
- This skill builds directly on `branch-review-loop`; if that skill's process changes, this
  skill inherits the change because Phase 2 above invokes it directly via the `Skill` tool
  rather than restating its logic.
- Closing out the loop's leftovers — its trivial issues and anything a non-clean stop left
  open — is the loop's own job, not this skill's. Do not add a cleanup pass here: it would
  duplicate work the loop already did and re-fix issues that no longer exist.
- No commit produced by this skill or its subagents should carry AI attribution (no
  `Co-Authored-By` lines, no agent credit) — this applies to the implementer's commit and every
  commit the review loop produces, round and finalize alike.
