---
name: design-review-loop
description: Iteratively review and fix a design plan until it converges (no substantive issues remain)
argument-hint: "<path to plan file>"
allowed-tools: Read, Write, Bash(git *), Bash(echo *), Bash(dirname *), Bash(mktemp *), Bash(wc *), Task
---

# Design Review Loop — Review → Fix → Repeat Until Clean

Iteratively harden the design plan at `$ARGUMENTS`. Each round, a **fresh** reviewer
agent runs the `design-review` process against the plan's *current* state, then a fixer
agent applies the confirmed fixes. The loop ends when a round surfaces no substantive
issues, when the work stops converging, when the plan starts growing faster than it converges,
or when a round cap is hit. A final pass then clears whatever the loop left behind — the
trivial issues it deliberately skipped each round, plus any substantive issues still open — so
the plan is handed back with no known open issues except the questions and fixes that genuinely
need the user's decision.

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
- **Reviewer agent** — a fresh `Task` agent (`subagent_type: "general-purpose"`) spawned each
  round. Runs `design-review` Phases 1–4 only and returns a structured issue list. By default uses
  whatever model the user currently has set — no override — since review quality should track the
  user's own model choice, not a fixed tier. A caller can explicitly request a different model for
  the reviewer (see Phase 0) — the same mechanism `branch-review-loop` offers — so a composite
  skill can get a stronger plan reviewer without restating this skill's process.
- **Fixer agent** — a `Task` agent (`subagent_type: "general-purpose"`, `model: "sonnet"`) spawned
  each round that has substantive issues. Edits the plan file to resolve them and reports what it
  changed. Fixing a confirmed, well-specified issue is comparatively mechanical, so `sonnet` is
  sufficient and keeps the loop cheaper.
- **Finalize agent** — a `Task` agent (`subagent_type: "general-purpose"`, `model: "sonnet"`)
  spawned at most once, after the loop ends, only if anything is left unresolved. Fixes the
  leftovers in one pass. Unlike the per-round fixer, its work is **not** re-reviewed — the point is
  to close out known issues, not to restart the loop.

## Process

### Phase 0: Preflight

1. Confirm `$ARGUMENTS` points to an existing plan file. If missing, ask the user for the path and stop.
2. Confirm the working tree is clean enough to commit the plan file per round
   (`git status --short -- <plan file>`). If the plan file already has uncommitted changes,
   commit them first so round commits are isolated. Run as two separate calls:
   `git add <plan file>`, then `git commit -m "design-review-loop: baseline"`. (A fixed string
   like this is safe inline; the meaningful per-round messages in Phase 4 are not — see there.)
3. Resolve the absolute path to the companion `design-review` skill. The reviewer runs as a
   subagent, which cannot use the Skill tool and does not share this skill's working directory,
   so it must be given an absolute filesystem path:
   !`echo "$(dirname "$CLAUDE_SKILL_DIR")/design-review/SKILL.md"`
   Use this absolute path wherever the reviewer prompt below says `<review skill path>`.
4. Generate a unique path for the round commit-message scratch file. The Write tool requires an
   absolute path, but a fixed name under `/tmp` collides if the user runs this loop on another
   branch or worktree at the same time — so mint one per invocation:
   !`mktemp -u /tmp/design-review-loop-commit-msg.XXXXXX`
   Use this exact path as `<commit msg path>` everywhere Phases 4 and 5 below reference it —
   each commit overwrites it, which is fine since commits are made one at a time.
5. Initialize round counter `N = 0`, an empty `history` of substantive issue summaries per
   round, and an empty `deferred` record of trivial issue summaries per round. Also record the
   plan's baseline line count (`wc -l <plan file>`) and start an empty record of per-round net
   line deltas.

Set a round cap of **5** by default. If the user asked for a different cap, use that instead.

Set a growth budget of **10%** of the baseline line count by default (see Phase 2's growth stop
condition). If the user asked for a different budget, use that instead.

Set no reviewer model override by default — the reviewer inherits the session's current model.
If the invocation explicitly requests a different model for the reviewer (e.g. "use opus for the
reviewer"), use that model instead everywhere Phase 1 spawns the reviewer agent.

### Phase 1: Review (fresh agent)

Increment `N`. Spawn a **new** reviewer agent, using the reviewer model resolved in Phase 0 (no
override by default, so it inherits the user's current model; an explicitly requested override
otherwise). Its prompt must contain **only** the plan path and the instructions below —
never the findings or context from previous rounds.

> Run the `design-review` skill's process (Phases 1–4) on the plan file at `<plan path>`.
> Read the review process from the file at `<review skill path>` and follow it exactly for
> Phases 1–4: gather context, identify candidate issues, verify them in parallel with `Explore`
> agents, and confirm which are real.
>
> **Do not run that skill's Phase 5** — do not ask the user anything and do not edit the plan.
>
> Return confirmed issues only, as a list, exactly in the structured format that skill's Phase 4
> defines — `severity`, `summary`, `section`, `why`, `fix` for each, with severity classified by
> that phase's definitions. That includes findings whose fix is a **deletion** — report them like
> any other confirmed issue, naming exactly what to delete. Keep the `requires user judgment:`
> prefix on any fix its Phase 4 says to mark that way. Also return any open questions its Phase 4
> puts in the `needs user decision` category, labeled as such — they must be reported so the loop
> can surface them, but they are never fixed and never counted as a design flaw.
>
> If there are no confirmed issues and no `needs user decision` questions, return exactly `NO ISSUES`.

Collect the reviewer's structured result.

### Phase 2: Decide whether to continue

Partition the confirmed issues into `substantive` and `trivial`. Set aside two kinds of item —
each is surfaced in the final summary, never fixed by this skill, and never counted as
substantive:

- `needs user decision` open questions.
- Confirmed issues whose `fix` carries the `requires user judgment:` prefix (`design-review`
  Phase 4). The finding is real, but its fix invents design surface — a new name, mechanism, or
  convention — that is the user's call, not an autonomous one.

Before applying the stop conditions, compare this round's issues against `deferred` (match by
summary/section, as for non-convergence). A re-report of a deferred trivial keeps its
**trivial** classification for stop-condition purposes regardless of the severity this round's
fresh reviewer assigned — reclassification by a reviewer who never saw the deferral is noise, not
escalation.

Stop the loop and go to **Phase 5** if any of these hold:

- **Clean:** there are no confirmed issues (`NO ISSUES`).
- **Nothing fixable remains:** there are zero substantive issues (only trivial issues,
  `needs user decision` questions, and/or `requires user judgment` items). Trivial issues are not
  fixed *inside* the loop — fixing them round after round invites churn and they are not worth
  re-reviewing — they are cleared once at the end by the Phase 5 finalize pass.
- **Round cap:** `N` has reached the cap (default 5).
- **Non-convergence:** the set of substantive issues this round is essentially the same as a
  previous round's (compare against `history` by summary/section). This means the fixer failed
  to resolve them or keeps reintroducing them — looping again will not help.
- **Oscillation / accretion:** substantive counts have failed to decline for **two consecutive
  rounds** — whether or not the issues are net-new. One round of net-new follow-ons after a fix
  is normal; two is the signature of a loop manufacturing its own review surface, where each fix
  enlarges the plan and the enlargement is the next round's finding.
- **Growth:** at least two rounds have been committed, the plan grew in every one of them, and
  its net growth over the Phase 0 baseline exceeds the growth budget (default 10%). A converging
  review shrinks or holds a plan as often as it grows one; monotonic growth means the loop is
  adding faster than it resolves.

Otherwise, record this round's substantive issue summaries in `history`, append this round's
trivial issue summaries to `deferred`, and continue to Phase 3.

### Phase 3: Fix (per-round agent)

Before spawning the fixer, print a summary of the substantive issues about to be fixed. Format it
as a short numbered list — one line per issue: `section: summary → fix`. Label it clearly, e.g.
`Round N — fixing X issue(s):`. This gives the user visibility into what is being changed before
any edits happen.

Spawn a fixer agent with `model: "sonnet"`, passing: the plan path and the **substantive**
issues from this round (summary, section, why, fix for each). Instruct it to:

> For each issue, edit the plan file at `<plan path>` to resolve it. Apply the suggested fix
> or a better one if the suggestion is wrong. Keep edits minimal and localized — change only
> what the issue requires; do not rewrite unrelated sections. Do not introduce new scope.
>
> When an issue's fix is a **deletion**, delete — do not soften it into a rewrite that keeps the
> text. Never add justification aimed at a future reviewer: if an issue's resolution is "the user
> decided X" or "risk Y is accepted", record it as a single line in the plan's `## Decisions`
> section (create the section if the plan lacks one), not as inline argument.
>
> When done, return a one-line description of each edit you made and the section you touched.

Trivial issues from this round are **not** sent to the fixer — only the last round's trivial
issues matter, and they are handled once by the Phase 5 finalize pass.

### Phase 4: Commit and loop

After the fixer returns, commit the plan file with a **meaningful message** that describes what was
actually fixed — not a generic round label. Build it from the fixer's reported edits:

1. Compose the commit message:
   - **Subject** (≤ 72 chars): a concise summary of the round's plan fixes, e.g.
     `Clarify migration ordering; resolve ambiguous rollback step`. If the round had many fixes,
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
3. Stage the plan file only — do not stage unrelated changes: `git add <plan file>`.
4. Commit: `git commit -F <commit msg path>`.
5. Record the new commit's short SHA and subject for the final summary, plus the round's net line
   delta for the plan file (from the commit's diffstat), then return to **Phase 1** with a fresh
   reviewer agent.

Run `git add` and `git commit` as **separate** Bash calls — never chained with `&&`. Each is then a
plain `git …` invocation that matches the `Bash(git *)` allowlist and clears the checker without a
prompt.

### Phase 5: Finalize — fix whatever the loop left behind

Gather everything the loop did not resolve, from the **last** review round only (earlier rounds'
issues were either fixed or re-reported by the next reviewer):

- Its trivial issues — never fixed inside the loop, by design.
- If the loop stopped on round cap, non-convergence, oscillation/accretion, or growth: its
  unresolved substantive issues too — the newest crop of real findings, not the least
  consequential leftovers.

`needs user decision` questions and `requires user judgment` issues are **never** sent to the
finalize agent — the first stay in `## Open Questions`, the second stay unfixed, and both are
surfaced in Phase 6 for the user.

If there is nothing left (the loop stopped clean, or only `needs user decision` /
`requires user judgment` items remain), skip this phase entirely — there is nothing to finalize
or commit.

Otherwise, print the list of items about to be fixed — one line each: `section: summary` — labeled
e.g. `Finalizing X leftover issue(s):`. Then spawn one finalize agent with `model: "sonnet"`,
passing the plan path and that list (summary, section, why, fix for each). Instruct it to:

> For each issue, edit the plan file at `<plan path>` to resolve it. Apply the suggested fix or a
> better one if the suggestion is wrong. Keep edits minimal and localized — change only what the
> issue requires; do not rewrite unrelated sections and do not introduce new scope. When an
> issue's fix is a **deletion**, delete rather than rewriting around the text, and never add
> justification aimed at a future reviewer — a resolution of the form "the user decided X" or
> "risk Y is accepted" belongs as one line in the plan's `## Decisions` section. If any issue
> cannot be resolved without a decision you are not in a position to make, leave it alone and say
> so rather than guessing. When done, return a one-line description of each edit you made and the
> section you touched, plus anything you deliberately left unfixed and why.

When it returns, commit the plan file using the **same commit protocol as Phase 4** (compose a
meaningful message, write it to `<commit msg path>` with the Write tool, `git add <plan file>`,
`git commit -F <commit msg path>`, each git call separate, no AI attribution). If the agent made
no edits, make no commit.

Do **not** re-review after this pass and do **not** re-enter the loop — this is a single closing
pass. Anything the finalize agent reports as deliberately left unfixed goes into the Phase 6
summary rather than being silently dropped.

### Phase 6: Final summary

When the loop and the finalize pass are done, output a concise report:

- **Outcome** — which stopping condition ended the loop (clean / nothing fixable / round cap /
  non-convergence / oscillation-accretion / growth).
- **Rounds run** — `N`, with a one-line note per round on what was found and fixed.
- **Plan size** — the baseline line count, each round's net delta, and the final count. Always
  report it, not only on a growth stop: it is the one signal that shows whether the loop
  hardened the plan or just inflated it.
- **Finalize pass** — what it cleared, or that there was nothing left to finalize. If it was
  handed unresolved *substantive* issues (an accretion, growth, cap, or non-convergence stop),
  say so plainly — those were real findings closed by an unreviewed pass.
- **Remaining issues** — anything the finalize agent left unfixed, so the user can decide what to
  do next.
- **Fixes left for the user** — confirmed issues whose fix was marked `requires user judgment`.
  List each with its section and suggested fix: they are real findings the loop deliberately did
  not apply because the fix would invent design surface the user should choose.
- **Open questions left for the user** — any open questions the reviewer returned in the
  `needs user decision` category (still in `## Open Questions`). Call these out explicitly rather
  than burying them among the rest — they are the one thing this skill deliberately does not
  resolve, in the loop or in the finalize pass.
- **Commits** — the per-round fix commits and the finalize commit (short SHA + subject line), so
  the user can review or revert the diff.

Do not prompt the user during the loop. If the loop stopped on non-convergence or the round cap
with substantive issues outstanding, say so plainly — the finalize pass takes one shot at them, and
whatever survives is reported, not looped on again.

## Notes

- Keep the reviewer's prompt free of prior-round context. This is the one invariant that makes the
  loop work; if you ever find yourself summarizing earlier findings into the reviewer prompt, stop.
- The orchestrator never edits the plan or runs the review itself — delegating both keeps its own
  context from accumulating round-over-round bias and keeps roles auditable via the per-round commits.
- The Phase 5 finalize pass is deliberately unreviewed. Re-reviewing it would restart the loop
  over changes that are usually the least consequential ones left — trivials the loop skipped. On
  a cap, non-convergence, accretion, or growth stop that is *not* true: the pass gets the last
  round's unresolved substantive issues, which is why Phase 6 must name them explicitly rather
  than filing them under routine cleanup. Either way it runs, and whatever it introduces is the
  accepted cost of never handing back a plan with known open issues — callers get that guarantee
  from this skill and should not re-implement it.
- This skill builds directly on `design-review`; if that skill's process changes, this loop inherits
  the change because the reviewer agent is told to follow the `design-review` SKILL.md at its
  resolved absolute path (`<review skill path>`). The issue fields, severity definitions, and the
  `needs user decision` category come from `design-review` Phase 4's output contract, not from
  this skill.
- `design-review-loop` and `branch-review-loop` are deliberate near-mirrors. When changing shared
  loop mechanics here (preflight, stop conditions, commit protocol, reviewer/fixer roles, model
  overrides), make the same change in the sibling skill — history shows they drift otherwise.
- Two mechanics here are **deliberately not mirrored** in `branch-review-loop`: the growth stop
  condition and the plan-size bookkeeping it needs. A plan's own bookkeeping (Files to Modify,
  step lists, rationale) turns every addition into a fresh consistency obligation a later
  reviewer will find violated, so an unbounded plan review accretes; diff size is not the
  analogous signal for code, where fixes are checked by tests rather than by whether five other
  sections re-enumerate them. The tightened oscillation/accretion rule *is* mirrored.
