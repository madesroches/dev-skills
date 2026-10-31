---
name: implement
description: Implement a design plan in full and commit the result, without running a review pass
argument-hint: "<path to plan file>"
allowed-tools: Read, Write, Bash(git *), Bash(mktemp *), Task, AskUserQuestion
---

# Implement — Build a Plan and Commit It

Implement the plan at `$ARGUMENTS` and commit the result. This skill does the implementation half
only: it never reviews the code it produced. Callers that want an independent review run a review
loop on the branch afterwards (`/implement-and-review` and `/ship-issue` both do).

**Model tiers.** This skill names models by role. `{{coding}}` is the tier for well-specified,
mechanical work — pass `model: "sonnet"`. `{{thinking}}` is the tier for judgment — pass
`model: "opus"`. To run on other models, remap those aliases with Claude Code's
`ANTHROPIC_DEFAULT_SONNET_MODEL` / `ANTHROPIC_DEFAULT_OPUS_MODEL`, or swap the two quoted
values for another alias (`sonnet`, `opus`, `haiku`, `fable`) here.

## Roles

- **Orchestrator** — this skill, running in the main context. Runs preflight, spawns the
  implementer, and relays its report. Does not write application code itself.
- **Implementer agent** — a `Task` agent (`subagent_type: "general-purpose"`, `model` =
  `{{coding}}`) spawned once. Reads the plan, implements every step, and commits the result.
  The `{{coding}}` tier is sufficient for well-specified implementation work coming from a plan
  document.

## Process

### Phase 0: Preflight

1. Confirm `$ARGUMENTS` is provided and points to an existing file. Read it. If missing or not
   found, say so and stop with a report whose first line begins `BLOCKED:` — do not guess a plan.
2. Resolve the repo's base branch: `git symbolic-ref --short refs/remotes/origin/HEAD`,
   stripping the `origin/` prefix; if that fails (no remote HEAD configured), fall back to
   `main`. Use this as `<base>` in step 4.
3. `git status --short` — the implementer commits its own changes, so the tree should be
   clean first. If there are uncommitted changes, show that output to the user and ask with
   AskUserQuestion whether to commit them as a baseline or stop — they may be unrelated WIP the
   user does not want swept into this run's history. If they choose to stop, stop here with a
   report whose first line begins `BLOCKED:`, before touching any branch — nothing has been
   created or switched yet, so stopping leaves the tree exactly as found. If they choose to
   commit, or the tree is already clean, continue to the next step.
4. Check the current branch: `git branch --show-current`. If it is `<base>`, or empty (detached
   HEAD — `--show-current` prints nothing there, which would otherwise be mistaken for "already
   on a feature branch"), the implementer must not commit directly onto it — create a feature
   branch first, before any commit below lands. Derive a short slug from the plan file's
   basename (lowercase, hyphens in place of spaces/underscores, extension stripped) and run
   `git checkout -b <slug>`. If the current branch is already something other than `<base>` and
   not detached, skip this — implement directly on it.
5. If step 3 called for a baseline commit, make it now, on top of the branch from step 4: stage
   by explicit path from the `git status --short` output — tracked and untracked alike — never
   `git add -A`, so nothing sweeps in silently. Run as two separate calls:
   `git add <file> [<file> ...]`, then `git commit -m "implement: baseline"`.
6. Generate a unique scratch path for the implementer's commit message (a fixed name under
   `/tmp` would collide across concurrent invocations):
   !`mktemp -u /tmp/implement-impl-commit-msg.XXXXXX`
   Use this exact path as `<impl commit msg path>`.

### Phase 1: Implement (`{{coding}}` agent)

Spawn one implementer agent with `model` = `{{coding}}`:

> Implement the plan at `<plan path>` in full. Read it carefully, then read whatever source
> files it references to confirm current state before editing. Follow the project's existing
> conventions (check `CLAUDE.md` if present). Implement every step in the plan — do not leave
> partial or stubbed work. If the project has fast, relevant checks (lint/tests for the
> touched areas), run them and fix any failures before committing.
>
> If the plan has a `## Manual Verification` section, run each step whose command is
> non-interactive and terminates on its own — skip anything needing a long-running server, a live
> external service, credentials you don't have, or human input, and say which you skipped and why.
> Report each command you ran with its actual output. If a step's result doesn't match the plan's
> expected result, fix the code before committing. **Do not convert these steps into automated
> tests** — the plan already decided they aren't worth maintaining as tests.
>
> When implementation is complete:
> 1. Compose a commit message: a concise subject (≤ 72 chars) summarizing the change, and a
>    body with one bullet per notable change. Write it to `<impl commit msg path>` with the
>    Write tool — do not pass it inline with `git commit -m`, since it may contain quotes or
>    other shell metacharacters.
> 2. Stage only the files you changed, by explicit path (`git add <file> ...`) — never
>    `git add -A`. Run `git add` and `git commit` as separate calls.
> 3. Commit with `git commit -F <impl commit msg path>`.
> 4. **Do not add a `Co-Authored-By` line or any AI/agent attribution to the commit message or
>    author identity.** The commit must read as if written entirely by the repository's normal
>    author.
>
> Return: the commit SHA, a one-line description of what you implemented, the results of any
> checks you ran, and the manual-verification steps you ran (with their output) or skipped. If
> you could not complete the plan (blocked, ambiguous, or failing checks you couldn't resolve),
> make the first line of your reply `BLOCKED:` followed by the reason, and do not commit a
> partial implementation.

### Phase 2: Report

End with a fixed report so callers can act on it without re-deriving anything:

- **Success** — the implementer's commit SHA, a one-line description, the checks it ran, and the
  manual-verification steps it ran (with their results) or skipped (with the reason).
- **Failure** — a first line beginning `BLOCKED:` and the blocker (from the implementer or from
  preflight). Callers detect blockage from that line and stop instead of reviewing an incomplete
  implementation.

## Notes

- This skill never reviews or cleans up after the implementer; that is a review loop's job, run
  by the caller. Keep the implementer and reviewer roles separate.
- No commit produced by this skill or its subagents should carry AI attribution (no
  `Co-Authored-By` lines, no agent credit).
