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

## Why direct `Skill` invocation (and not read-as-text)

`implement-and-review` reads `branch-review-loop`'s file and follows it as *text* because it must
deviate from it (override the reviewer's model to `opus`, raise the round cap). `ship-issue` needs
**no deviation** from any of the four skills it chains — it wants each run verbatim. So it invokes
each one through the `Skill` tool. Each invoked skill then executes its own preflight, its own
`!`-prefixed commands, and its own subagents natively, which the read-as-text pattern cannot do.
Because nothing is restated, any change to a sub-skill's process is inherited automatically.

## Roles

- **Orchestrator** — this skill, in the main context. Sequences the four sub-skills, does the
  git/`gh` connective work, commits the plan once, and writes the final summary. It does not
  design, review, implement, or open the PR itself.
- **`design`** — invoked with the issue reference. Researches the codebase and writes the plan
  document. Produces no code.
- **`design-review-loop`** — invoked with the plan path. Autonomously reviews and fixes the plan
  until it converges, committing each round.
- **`implement-and-review`** — invoked with the plan path. Implements the plan (sonnet), commits,
  runs the `opus` `branch-review-loop`, then finalizes.
- **`pr`** — invoked with no arguments. Runs lints/tests, moves the plan to `tasks/completed/`,
  updates the changelog, pushes, and opens the PR.

## Process

### Phase 0: Preflight

1. Confirm `$ARGUMENTS` is provided and looks like a GitHub issue reference (a full issue URL or
   an issue number). If missing, say so and stop — do not invent an issue.
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
   detached, skip this — work on it directly.
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
2. Capture the plan file path from `design`'s output (its Phase 5 reports the path). If `design`
   did not produce a plan — because it stopped with open questions, could not fetch the issue, or
   otherwise blocked — relay that to the user and **stop**. Do not fabricate a plan path or proceed
   to review.
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

Invoke the `design-review-loop` skill via the `Skill` tool, passing the **plan path** as its
arguments. It runs autonomously, committing after each fix round, and terminates on its own
(clean / only-trivial / round cap / non-convergence). Note its reported outcome for the final
summary, then continue regardless — a non-clean stop leaves remaining issues that
`implement-and-review`'s own review pass and the plan's reviewers can still surface.

### Phase 3: Implement and independently review

Invoke the `implement-and-review` skill via the `Skill` tool, passing the **plan path** as its
arguments. Its own preflight will find an existing feature branch (created in Phase 0) and a clean
tree (the review loop committed its rounds), so it implements in place. It implements the plan,
commits, runs the `opus` review loop, and finalizes.

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
- `design-review-loop`'s outcome (converged, or which stopping condition fired + any remaining issues).
- `implement-and-review`'s outcome (implementer commit, review-loop convergence status, finalize commit — or the blocker it stopped on).
- The PR URL, or the phase at which the chain stopped and why.

## Notes

- **Branch up front.** Creating the feature branch in Phase 0 is what keeps the plan commit, every
  review-loop round, and the implementation on one branch. Do not defer branch creation to
  `implement-and-review` — by then the plan and review commits would already have landed on
  `<base>`.
- **Fail-stop between stages.** Stop and hand back if `design` produced no plan, if
  `implement-and-review`'s implementer was blocked, or if `pr`'s checks failed. Never carry a
  broken chain forward into a PR.
- **No AI attribution** on the one commit this skill makes (the plan commit) — and the sub-skills
  already enforce the same for every commit they make.
- **No restated logic.** Every stage is a direct `Skill` invocation with no per-skill deviation,
  so a change to any of `design`, `design-review-loop`, `implement-and-review`, or `pr` is
  inherited here automatically.
