---
name: implement-and-review
description: Implement a design plan, commit it, then iteratively review and fix the branch with a stronger model until it converges
argument-hint: "<path to plan file>"
allowed-tools: Read, Skill, Bash(git symbolic-ref *)
---

# Implement and Review — Build a Plan, Then Harden It

Implement the plan at `$ARGUMENTS`, commit the result, then run the `branch-review-loop`
process against the resulting branch to catch and fix anything the implementation missed.
The review loop's reviewer runs on the `{{thinking}}` tier regardless of the session's current
model — this skill exists specifically to pair fast implementation with a stronger, independent
review pass.

**Model tiers.** This skill names models by role. `{{coding}}` is the tier for well-specified,
mechanical work — pass `model: "sonnet"`. `{{thinking}}` is the tier for judgment — pass
`model: "opus"`. To run on other models, remap those aliases with Claude Code's
`ANTHROPIC_DEFAULT_SONNET_MODEL` / `ANTHROPIC_DEFAULT_OPUS_MODEL`, or swap the two quoted
values for another alias (`sonnet`, `opus`, `haiku`, `fable`) here.

This skill is a thin wrapper: it holds no implementation or review logic of its own, only the
sequencing of `dev-skills:implement` and a review loop. The review loop closes out its own
leftovers (its trivial issues and anything a non-clean stop left open) in its final phase, so this
skill does not add a cleanup pass of its own.

## Roles

- **Orchestrator** — this skill, running in the main context. Sequences implementation then
  review and writes the final summary. Does not write application code or review it itself.
- **Implementation** — delegated to the `dev-skills:implement` skill via the `Skill` tool,
  passing the plan path. It runs its own preflight (dirty tree, feature branch), spawns the
  `{{coding}}` implementer, commits, and ends with a fixed report.
- **Review loop** — delegated directly to the `dev-skills:branch-review-loop` skill via the `Skill` tool,
  passing the base branch, a round cap of 10, and a request to use the `{{thinking}}` tier for the
  reviewer (in autonomous mode: `autonomous-branch-review-loop`, no round cap) —
  parameters that skill's own Phase 0 already supports, so this is not a deviation from its
  process, just arguments it's designed to take. It also runs its own finalize pass at the end,
  clearing the trivial issues it skips each round and anything a non-clean stop left open. This
  skill automatically inherits any change to either skill's logic since nothing is restated.

## Process

### Phase 0: Preflight

Confirm `$ARGUMENTS` is provided and points to an existing file. Read it. If missing or not
found, say so and stop — do not guess a plan. If the arguments also request `autonomous mode`
(e.g. `<plan path> — autonomous mode`), note it: Phase 2 then uses the autonomous review loop. It
is off by default. Everything else — dirty-tree handling, the feature branch, the baseline commit —
is `dev-skills:implement`'s preflight.

### Phase 1: Implement

Invoke the `dev-skills:implement` skill via the `Skill` tool, passing the **plan path** only (strip
any `autonomous mode` text). If its report begins `BLOCKED:` (could not complete the plan, or
failing checks it could not resolve), relay that and **stop** — do not proceed to review an
incomplete implementation. Otherwise keep its report (the SHA is in it, so no separate `git log`
confirmation is needed) for the summary.

### Phase 2: Review loop (`{{thinking}}`)

Resolve the repo's base branch the way `implement` does: `git symbolic-ref --short
refs/remotes/origin/HEAD`, stripping the `origin/` prefix; if that fails (no remote HEAD
configured), fall back to `main`. Use this as `<base>`.

Then invoke the `dev-skills:branch-review-loop` skill via the `Skill` tool, passing: the base
branch `<base>`, an instruction to use a round cap of 10, and an instruction to use the
`{{thinking}}` tier for the reviewer (e.g. `<base> — use the {{thinking}} tier for the reviewer and
a round cap of 10`). It runs its whole process autonomously — including its own baseline-commit
check, which will find nothing to do since the tree is already clean after Phase 1's commit —
committing after each fix round, terminating on its own (clean / only trivial / round cap /
non-convergence / oscillation-accretion / reviewer failure), and then running its own finalize
pass over whatever it left unresolved.

**Autonomous mode** (set in Phase 0): invoke `dev-skills:autonomous-branch-review-loop` instead, passing
`<base> — use the {{thinking}} tier for the reviewer` (no round cap). The loop can then stop only on clean / only
trivial / non-convergence / escalation / reviewer failure — it has no round cap and no
oscillation-accretion stop — so read the stop-condition list above, and Phase 3's convergence wording, as limited to
those.

Record which stopping condition ended the loop, plus what its finalize pass cleared and anything
it reported as still unfixed. Treat "clean" as **converged**; every other stopping condition
(including "only trivial", since that means substantive issues were resolved but something was
still left over for the finalize pass) as **did not fully converge** — be precise about which one
it actually was.

### Phase 3: Final summary

Report:
- The implementer's commit (SHA + one-line description) and any checks it ran, from
  `dev-skills:implement`'s report.
- The manual-verification steps the implementer ran (with their results), and any it skipped
  (with the reason).
- The review loop's outcome: rounds run, per-round fix commits, and the **convergence
  status** — state plainly whether it converged (stopped clean) or did not (hit the round cap,
  stopped with only trivial issues remaining, or stopped on non-convergence or
  oscillation/accretion with issues still outstanding at that point — in autonomous mode only
  the loop's own stops apply, with escalation in place of round cap and oscillation/accretion — or on reviewer failure, in which
  case the last fix round went unreviewed, or no review completed if it failed in round 1).
- Its finalize pass: the commit it made (SHA + what it fixed), or that nothing was left to
  finalize — and any issue it reported as deliberately left unfixed.

## Notes

- Keep the implementer and reviewer roles separate — the implementer never reviews its own
  work, and the reviewer starts each round from a blank context with no memory of prior rounds'
  findings, though it does read the branch's plan file for recorded verification decisions. This
  mirrors why `branch-review-loop` always starts its reviewer from a blank context.
- This skill builds directly on `implement` and `branch-review-loop`; if either skill's process
  changes, this skill inherits the change because Phases 1 and 2 invoke them directly via the
  `Skill` tool rather than restating their logic.
- Closing out the loop's leftovers — its trivial issues and anything a non-clean stop left
  open — is the loop's own job, not this skill's. Do not add a cleanup pass here: it would
  duplicate work the loop already did and re-fix issues that no longer exist.
- No commit produced by this skill or its sub-skills should carry AI attribution (no
  `Co-Authored-By` lines, no agent credit) — this applies to the implementer's commit and every
  commit the review loop produces, round and finalize alike.
