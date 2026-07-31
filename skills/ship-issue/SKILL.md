---
name: ship-issue
description: Take a GitHub issue from design through review, implementation, and a pull request in one autonomous chain
argument-hint: "<issue url or number>"
allowed-tools: Skill, Bash(git *), Bash(gh issue view *), Bash(mktemp *), Read, Edit, Write, AskUserQuestion
---

# Ship Issue — From Issue to Pull Request

Take the GitHub issue at `$ARGUMENTS` all the way to a pull request by sequencing the repo's
existing skills: write a design plan (`design`) and commit it, harden that plan
(`design-review-loop`), implement and independently review the result (`implement-and-review`),
then finalize and open the PR (`pr`).

This skill is **connective tissue only**. It does not itself write the plan, review it,
implement code, or open the PR — each of those is delegated to the corresponding skill,
**invoked directly via the `Skill` tool** and run exactly as designed. The orchestrator's own
work is limited to preflight (fetch the issue, create the branch), one commit of the plan file,
and relaying each stage's outcome.

## Autonomy — run the whole chain without pausing

This chain is **autonomous end to end**. Once preflight succeeds, run every phase to completion in
one continuous pass, moving straight from each stage into the next **in the same turn** — do not
yield the turn to the user between phases. A brief summary of a stage's outcome is fine, but it
must be immediately followed by the next stage; it is never a place to stop and wait.

The **only** things that stop the chain are the hard blockers enumerated per phase: no issue
reference given, the issue can't be fetched, `design` produced **no plan file at all**,
`implement-and-review`'s implementer was **blocked**, or `pr`'s checks failed. Nothing else halts
it. In particular:

- **Open questions are not a stop condition.** `design` routinely lists open questions in its
  output — that is normal, and it does not mean the plan is incomplete. Resolving them is the job of
  the next stage: `design-review` treats every open question as a candidate to answer from the
  codebase, and the `design-review-loop` fixer folds those answers into the plan. Only the rare
  open question the code genuinely cannot settle is left in `## Open Questions` for the user. So do
  not stop, and do not ask the user to answer open questions, just because `design` surfaced them —
  hand them to Phase 2.
- The one exception is a genuine **hard requirement for the user's judgment** — a decision the
  chain cannot make on its own without risking wrong or destructive work (e.g. an irreversible
  action, or ambiguity that would send the whole implementation down the wrong path). Only then
  pause with `AskUserQuestion`. A routine open question or a plan the user might merely *prefer* to
  tweak does not qualify.

## Autonomous push — remind the user up front

The final phase (`pr`) pushes the branch, which is what lets CI run on the resulting PR. That push
can be gated by the permission layer: some repos' `CLAUDE.md` require a **direct, unambiguous
instruction to push**, and an autonomous chain on its own does not satisfy that — so the push (and
therefore CI) can stall even though every earlier stage succeeded. The skill cannot override that
gate, but the user can pre-authorize it simply by giving an explicit push instruction, which then
sits in context when `pr` reaches the push.

So **at the very start of the run** (Phase 0), check whether the user's invocation already carries
an explicit push instruction (e.g. "and push", "push and open the PR"). If it does, the chain is
fully autonomous through the PR — say nothing about it. If it does **not**, emit a one-line reminder
before proceeding: that the chain will run straight through, but the final push may be gated unless
they've explicitly asked for it, and that re-invoking with an explicit push instruction (e.g.
`/ship-issue <issue> — push and open the PR when done`) makes the whole run, push included,
autonomous. Then **continue the chain anyway without pausing** — do not wait for a reply. If the
push does end up gated at Phase 4, `pr` stops there with the branch and all commits intact, and the
user already knows why and how to avoid it next time.

## Why direct `Skill` invocation (and not read-as-text)

`ship-issue` needs **no deviation** from any of the four skills it chains — it wants each run
verbatim, following each skill's own supported inputs. So it invokes each one through the `Skill`
tool, passing `design-review-loop` a higher round cap (Phase 2) and `implement-and-review` the
plan path, the same way a user would — arguments each skill's own Phase 0 already knows how to
honor, not a change to its process. Each invoked skill then executes its own preflight, its own
`!`-prefixed commands, and its own subagents natively. Because nothing is restated, any change to
a sub-skill's process is inherited automatically. `implement-and-review` itself follows the same
principle one layer down: it delegates its review loop to `branch-review-loop` via the `Skill`
tool (passing an `opus` reviewer override and a round cap of 10), rather than restating that
loop's process — so this chain never restates any skill's logic at any level.

## Roles

- **Orchestrator** — this skill, in the main context. Sequences the four sub-skills, does the
  git/`gh` connective work, commits the plan once, and writes the final summary. It does not
  design, review, implement, or open the PR itself.
- **`design`** — invoked with the issue reference. Researches the codebase and writes the plan
  document. Produces no code.
- **`design-review-loop`** — invoked with the plan path and a round cap of 10 (double its own
  default). Autonomously reviews and fixes the plan until it converges, committing each round,
  then clears its own leftovers in a final pass.
- **`implement-and-review`** — invoked with the plan path. Implements the plan (sonnet), commits,
  and runs the `opus` `branch-review-loop`, which reviews, fixes, and finalizes.
- **`pr`** — invoked with no arguments. Runs lints/tests, moves the plan to `tasks/completed/`,
  updates the changelog, pushes, and opens the PR.

## Process

### Phase 0: Preflight

1. Confirm `$ARGUMENTS` is provided and looks like a GitHub issue reference (a full issue URL or
   an issue number). If missing, say so and stop — do not invent an issue.
   Then apply the **Autonomous push** check above: if the invocation carries no explicit push
   instruction, emit the one-line reminder now, before proceeding — and continue without pausing.
2. Confirm the issue exists and capture its metadata:
   `gh issue view <issue> --json number,title,url`. If the command fails (bad number, wrong repo,
   not authenticated), report the error and stop. Keep the issue's **number**, **title**, and
   **url** — they are used for the branch slug, the plan's issue link, and the plan commit subject.
3. Resolve the repo's base branch: `git symbolic-ref --short refs/remotes/origin/HEAD`, stripping
   the `origin/` prefix; if that fails (no remote HEAD configured), fall back to `main`. Use this
   as `<base>`.
4. `git status --short` — downstream skills commit as they go, so the tree should be clean first.
   If there are uncommitted changes, show that output to the user and ask with AskUserQuestion
   whether to commit them as a baseline or stop — they may be unrelated WIP the user does not want
   swept into this run's history. If they choose to stop, stop here, before any branch is created
   or switched — the tree is left exactly as found. Otherwise continue.
5. Check the current branch: `git branch --show-current`. If it is `<base>`, or empty (detached
   HEAD — `--show-current` prints nothing there, which would otherwise be mistaken for "already on
   a feature branch"), create a feature branch now so that every downstream commit lands on it and
   not on `<base>`. Derive a slug from the issue: `<number>-<title-slug>`, where `<title-slug>` is
   the title lowercased, non-alphanumeric runs collapsed to single hyphens, leading/trailing
   hyphens trimmed, and truncated to a reasonable length (e.g. `142-add-zoom-buttons`). Run
   `git checkout -b <slug>`. If the current branch is already something other than `<base>` and not
   detached, check that it plausibly belongs to this issue: does the branch name contain the
   issue number? If it does, skip branch creation and work on it directly. If it does not, ask
   with AskUserQuestion (this is preflight — the no-pausing rule applies only once the chain is
   running) whether to (a) continue on the current branch anyway, (b) create the issue's feature
   branch off `<base>` (`git checkout -b <slug> <base>`) and work there, or (c) stop — otherwise
   the whole chain (plan, review rounds, implementation, PR) could silently pile onto a branch
   made for unrelated work.
6. If step 4 called for a baseline commit, make it now, on top of the branch from step 5: stage by
   explicit path from the `git status --short` output — tracked and untracked alike — never
   `git add -A`. Run as two separate calls: `git add <file> [<file> ...]`, then
   `git commit -m "ship-issue: baseline"`.
7. Mint a unique scratch path for the plan commit message (the issue title may contain quotes or
   other shell metacharacters, so the message is written to a file and committed with `-F` rather
   than passed inline):
   !`mktemp -u /tmp/ship-issue-plan-commit-msg.XXXXXX`
   Use this exact path as `<plan commit msg path>`.

### Phase 1: Design the plan, then commit it

1. Invoke the `design` skill via the `Skill` tool, passing the **issue reference** (`$ARGUMENTS`)
   as its arguments. Let it fetch the issue and write the plan; do not pre-empt its research.
2. Capture the plan file path from `design`'s output (its Phase 5 reports the path). A plan that
   lists **open questions** is still a complete plan — `design` surfaces open questions as a normal
   part of its Phase 5 output, and they are resolved downstream by `design-review-loop` and
   `implement-and-review`, not by pausing here. Open questions are **not** a stop condition, and are
   never a reason to ask the user anything at this point. Stop **only** if `design` produced no plan
   file at all — e.g. it could not fetch the issue or was otherwise hard-blocked — in which case
   relay that and **stop**. Do not fabricate a plan path, and otherwise proceed immediately to
   step 3 without yielding the turn.
3. **Record the issue link in the plan** so the downstream `pr` skill can auto-link it. Read the
   plan file. If it does not already contain a `**GitHub Issue**:` line near the top, insert one
   in the plan's header — on its own line just below the `# <Title> Plan` heading — using the
   issue **url** from Phase 0, e.g. `**GitHub Issue**: https://github.com/owner/repo/issues/142`.
   If such a line is already present, leave it.
4. Commit the plan file:
   - Compose a commit message — subject: `Add design plan for #<number>: <title>` (truncate to
     ≤ 72 chars); body optional. Write it to `<plan commit msg path>` with the **Write** tool.
   - `git add <plan path>` (the plan file only, by explicit path).
   - `git commit -F <plan commit msg path>`.
   - **No AI attribution** — no `Co-Authored-By` line, no agent credit.
   Run `git add` and `git commit` as separate calls.

### Phase 2: Harden the plan

Invoke the `design-review-loop` skill via the `Skill` tool, passing the **plan path** followed by
an instruction to use a round cap of **10** instead of its own default of 5 (e.g. `<plan path> —
use a round cap of 10`) — that skill's own Phase 0 already supports a user-specified cap, so this
is not a deviation from its process, just an argument it's designed to take. It runs autonomously,
committing after each fix round, terminates on its own (clean / nothing fixable / round cap /
non-convergence), and then clears whatever it left unresolved in its own finalize pass. Note its
reported outcome for the final summary, then continue regardless — anything its finalize pass left
unfixed, plus any `needs user decision` open questions, is carried forward, not stopped on: the
implementation stage and its review pass can still surface what matters.

### Phase 3: Implement and independently review

Invoke the `implement-and-review` skill via the `Skill` tool, passing the **plan path** as its
arguments. Its own preflight will find an existing feature branch (created in Phase 0) and a clean
tree (the review loop committed its rounds), so it implements in place. It implements the plan,
commits, and runs the `opus` review loop, which reviews, fixes, and finalizes on its own.

If it reports the implementer was **blocked** (could not complete the plan, or failing checks it
could not resolve), relay that and **stop** — do not proceed to open a PR for an incomplete
implementation. Otherwise note its outcome (implementer commit, review-loop convergence status,
finalize commit) and continue.

### Phase 4: Open the pull request

Invoke the `pr` skill via the `Skill` tool with **no arguments**. It runs the project's
lints/tests for the changed areas, moves the plan to `tasks/completed/`, updates the changelog,
pushes the branch, and opens the PR — discovering the issue to link from the `**GitHub Issue**:`
line added in Phase 1.

If `pr` stops before creating the PR (e.g. a lint or test failure — it does not open a PR on a
failing check), relay exactly what it reported needs fixing and **stop** at this phase. The branch
and all commits are intact; the user (or a follow-up run) can fix and re-run `/pr`.

### Phase 5: Final summary

Report the whole chain concisely:
- The issue (number + title) and the branch it was shipped on.
- The plan file path and its commit.
- `design-review-loop`'s outcome (converged, or which stopping condition fired), what its finalize
  pass cleared, and any open questions it left for the user.
- `implement-and-review`'s outcome (implementer commit, review-loop convergence status, the loop's
  finalize commit — or the blocker it stopped on).
- The PR URL, or the phase at which the chain stopped and why.

## Notes

- **Branch up front.** Creating the feature branch in Phase 0 is what keeps the plan commit, every
  review-loop round, and the implementation on one branch. Do not defer branch creation to
  `implement-and-review` — by then the plan and review commits would already have landed on
  `<base>`.
- **Fail-stop between stages, but only on hard blockers.** Stop and hand back only if `design`
  produced no plan file at all, if `implement-and-review`'s implementer was blocked, or if `pr`'s
  checks failed — never carry a broken chain forward into a PR. Everything short of those (open
  questions, minor review findings, non-clean loop stops) is carried forward, not stopped on. See
  **Autonomy** above.
- **No AI attribution** on the one commit this skill makes (the plan commit) — and the sub-skills
  already enforce the same for every commit they make.
- **No restated logic.** Every stage is a direct `Skill` invocation with no per-skill deviation,
  so a change to any of `design`, `design-review-loop`, `implement-and-review`, or `pr` is
  inherited here automatically. `implement-and-review` carries this same principle one layer
  further down for its own review loop — see **Why direct `Skill` invocation** above.
