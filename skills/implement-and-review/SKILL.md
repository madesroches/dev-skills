---
name: implement-and-review
description: Implement a design plan, commit it, then iteratively review and fix the branch with a stronger model until it converges
argument-hint: "<path to plan file>"
allowed-tools: Read, Write, Bash(git *), Bash(dirname *), Bash(mktemp *), Bash(echo *), Task
---

# Implement and Review — Build a Plan, Then Harden It

Implement the plan at `$ARGUMENTS`, commit the result, then run the `branch-review-loop`
process against the resulting branch to catch and fix anything the implementation missed.
The review loop's reviewer runs under `opus` regardless of the session's current model — this
skill exists specifically to pair fast implementation with a stronger, independent review pass.

## Roles

- **Orchestrator** — this skill, running in the main context. Sequences implementation then
  review, resolves paths, and writes the final summary. Does not write application code or
  review it itself.
- **Implementer agent** — a `Task` agent (`subagent_type: "general-purpose"`, `model: "sonnet"`)
  spawned once. Reads the plan, implements every step, and commits the result. `sonnet` is
  sufficient for well-specified implementation work coming from a plan document.
- **Review loop** — carried out by the orchestrator itself (not delegated to a subagent),
  following the `branch-review-loop` skill's process verbatim from its file on disk, so this
  skill automatically inherits any change to that loop's logic. Three deviations: its Phase 1
  reviewer agent is spawned with `model: "opus"` instead of no override, its round cap
  defaults to 10 instead of 5, and its own Phase 0 step 4 (resolving `<review skill path>`) is
  skipped in favor of the path already resolved in this skill's own Phase 0.
- **Finalize agent** — a `Task` agent (`subagent_type: "general-purpose"`, `model: "sonnet"`)
  spawned once after the review loop ends, only if it left anything unresolved (the trivial
  issues it never fixes by design, plus any substantive issues still open because the loop hit
  its round cap or stopped on non-convergence). Fixes all of it and commits. Unlike the loop's
  own fixer, this pass has no follow-up review — it exists so the skill never hands back a
  branch with known, unaddressed issues just because they were labeled "trivial" or the cap
  was reached.

## Process

### Phase 0: Preflight

1. Confirm `$ARGUMENTS` is provided and points to an existing file. Read it. If missing or
   not found, say so and stop — do not guess a plan.
2. Resolve the repo's base branch: `git symbolic-ref --short refs/remotes/origin/HEAD`,
   stripping the `origin/` prefix; if that fails (no remote HEAD configured), fall back to
   `main`. Use this as `<base>` here and in Phase 2. Then check the current branch:
   `git branch --show-current`. If it is `<base>`, the implementer must not commit directly to
   it — create a feature branch first, before any other Phase 0 step touches the tree, so the
   baseline commit (step 3) and every later commit land on the new branch instead of `<base>`.
   Derive a short slug from the plan file's basename (lowercase, hyphens in place of
   spaces/underscores, extension stripped) and run `git checkout -b <slug>`. If the current
   branch is already something other than `<base>`, skip this — implement directly on it.
3. `git status --short` — the implementer commits its own changes, so the tree should be
   clean first. If there are uncommitted changes, show them to the user and commit them as a
   baseline so the implementation commit stays isolated. Stage by explicit path from the
   `git status --short` output — never `git add -A`. Run as two separate calls:
   `git add <file> [<file> ...]`, then `git commit -m "implement-and-review: baseline"`.
4. Resolve the absolute path to the companion `branch-review-loop` skill (needed for Phase 2 —
   `$CLAUDE_SKILL_DIR` here points at this skill's own directory, not that one):
   !`echo "$(dirname "$CLAUDE_SKILL_DIR")/branch-review-loop/SKILL.md"`
   Use this absolute path wherever Phase 2 below says `<loop skill path>`.
5. Also resolve the absolute path to the companion `branch-review` skill directly, here in this
   skill's own Phase 0 — do not rely on `branch-review-loop`'s own Phase 0 step 4 to do this when
   its file is merely read and followed as text rather than invoked as a skill — its `!`-prefixed
   command does not execute, and `$CLAUDE_SKILL_DIR` cannot be trusted to still point at
   `branch-review-loop`'s directory at that point:
   !`echo "$(dirname "$CLAUDE_SKILL_DIR")/branch-review/SKILL.md"`
   Use this absolute path as `<review skill path>` wherever the loop file (followed in Phase 2)
   says `<review skill path>` — do not let the loop file's own (inert) Phase 0 step 4 resolve it.
6. Generate a unique scratch path for the implementer's commit message (a fixed name under
   `/tmp` would collide across concurrent invocations):
   !`mktemp -u /tmp/implement-and-review-impl-commit-msg.XXXXXX`
   Use this exact path as `<impl commit msg path>`.
7. Generate a unique scratch path for the finalize commit message:
   !`mktemp -u /tmp/implement-and-review-finalize-commit-msg.XXXXXX`
   Use this exact path as `<finalize commit msg path>`.

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

Confirm the implementer's commit landed (`git log --oneline -1`). Then carry out the
`branch-review-loop` process yourself, in this same context, exactly as written in the file at
`<loop skill path>` — its Phases 0 through 5, targeting base branch `<base>` (resolved in
this skill's Phase 0 step 2) — with these
deviations, which take precedence over the loop file's own wording wherever they conflict with it:

> Skip that skill's own Phase 0 step 4 (resolving `<review skill path>`) — it is a no-op here
> since that file is being followed as text, not invoked as a skill. Use the `<review skill
> path>` already resolved in this skill's own Phase 0 step 5 instead, everywhere the loop file
> says `<review skill path>`.
>
> In that skill's Phase 1, spawn the reviewer agent with `model: "opus"` explicitly — this
> overrides that phase's "no `model` override — inherits the user's current model" instruction
> and its restatement as an invariant in that skill's Roles section; wherever the two conflict, this
> skill's `opus` override wins. In its Phase 0, use a round cap of **10** instead of the default
> 5. Everything else — the fixer's `model: "sonnet"`, the per-round commit behavior, the
> convergence/stopping rules, and the final summary — applies unchanged. As with every commit
> this skill makes or causes to be made, round commits must carry no AI attribution.

Since the tree is already clean after Phase 1's commit, that skill's own baseline-commit step
in its Phase 0 will find nothing to do.

Record which stopping condition ended the loop (clean / only trivial / round cap /
non-convergence / oscillation) — Phase 4 reports this as the convergence status. Treat "clean"
as **converged**; every other stopping condition (including "only trivial", since that means
substantive issues were resolved but something is still left over) as **hit the round cap /
did not fully converge** — be precise about which one it actually was.

### Phase 3: Finalize — fix whatever the loop left behind

Gather everything the review loop did not resolve:
- Trivial issues from its last review round (never fixed by the loop, by design).
- If the loop stopped on round cap, non-convergence, or oscillation: the unresolved
  substantive issues from its last round too.

If there is nothing left (the loop stopped clean with zero confirmed issues), skip this phase
entirely — there is nothing to finalize or commit.

Otherwise, print the list of items about to be fixed (one line each: `file: summary`), then
spawn one finalize agent with `model: "sonnet"`, passing that list:

> For each issue, edit the code to resolve it. Apply the suggested fix or a better one if the
> suggestion is wrong. Keep edits minimal and localized. If the project has fast, relevant
> checks for the touched files, run them to confirm your edits don't break the build.
>
> When done: compose a commit message (concise subject + one bullet per edit), write it to
> `<finalize commit msg path>` with the Write tool, stage only the files you changed by
> explicit path, and commit with `git commit -F <finalize commit msg path>`. **Do not add a
> `Co-Authored-By` line or any AI/agent attribution.**
>
> Return a one-line description of each edit you made and the file you touched.

If the finalize agent reports it could not resolve something (e.g. a substantive issue that
needs a design decision), note that in the final summary rather than silently dropping it.

### Phase 4: Final summary

Report:
- The implementer's commit (SHA + one-line description) and any checks it ran.
- The review loop's outcome: rounds run, per-round fix commits, and the **convergence
  status** — state plainly whether it converged (stopped clean) or did not (hit the round cap,
  stopped with only trivial issues remaining, or stopped on non-convergence/oscillation with
  issues still outstanding at that point).
- The finalize commit, if one was made (SHA + what it fixed), or note that nothing was left to
  finalize.

## Notes

- Keep the implementer and reviewer roles separate — the implementer never reviews its own
  work, and the reviewer never sees the plan, only the resulting diff. This mirrors why
  `branch-review-loop` always starts its reviewer from a blank context.
- This skill builds directly on `branch-review-loop`; if that skill's process changes, this
  skill inherits the change because Phase 2 above follows it at its resolved absolute path
  rather than restating its logic.
- The finalize pass is deliberately unreviewed — it exists to guarantee the branch this skill
  hands back has no known open issues, not to re-run the loop. If it introduces a new problem,
  that's a cost accepted for closing out every round's leftovers in one pass.
- No commit produced by this skill or its subagents should carry AI attribution (no
  `Co-Authored-By` lines, no agent credit) — this applies to the implementer's commit, every
  round commit the review loop produces, and the finalize commit.
