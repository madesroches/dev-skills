# Autonomous Review Loops and Ship-Auto Plan

## Overview

Add three skills:

- `/autonomous-branch-review-loop` and `/autonomous-design-review-loop` are variants of the two
  review loops. They have no round cap and keep looping as long as reviewers raise substantive
  issues. They fix trivial issues in the round they appear instead of deferring them all to the
  finalize pass. Because a fresh, stateless reviewer now drives trivial fixes every round, the
  loop keeps a ledger of the trivial fixes it has already applied. It refuses to re-apply,
  refine, or reverse any of them, so a nit fixed in round 2 can't be flipped back in round 3.
- `/ship-auto` is `/ship-issue` for a user who is assumed AFK (issue-only, matching `ship-issue`). It chains design → autonomous plan
  loop → implementation → autonomous branch loop → PR. It never prompts: wherever a skill in the
  chain would ask, it takes a recorded default instead. When it finishes (or hard-stops), it lists
  the most important decisions it took on the user's behalf.

## Current State

- `skills/branch-review-loop/SKILL.md` and `skills/design-review-loop/SKILL.md` are near-mirror
  loops (review → fix → commit, fresh reviewer each round, then an unreviewed finalize pass).
  - Round cap: 5 by default, caller-overridable (`branch-review-loop` line 88,
    `design-review-loop` line 80).
  - Trivial issues are never fixed in-round. Phase 3 sends only substantive issues to the fixer.
    Trivials go to a `deferred` record, and only the **last** round's trivials reach the Phase 5
    finalize agent. Phase 2's re-report rule keeps a re-reported deferred trivial trivial,
    whatever severity the fresh reviewer gives it.
  - Phase 2 stop conditions: clean, only-trivial (nothing fixable, in the design loop), round
    cap, non-convergence, oscillation/accretion, and growth (design loop only).
- Callers change a skill's behavior through arguments in that skill's own Phase 0 (round cap,
  reviewer model). Composite skills invoke other skills via the `Skill` tool rather than
  restating them (`skills/implement-and-review/SKILL.md:102`).
- `skills/ship-issue/SKILL.md` chains `design` → `design-review-loop` (cap 10) →
  `implement-and-review` → `pr`. It can block on user input at these points:
  - Phase 0 step 4: dirty tree, commit as baseline or stop.
  - Phase 0 step 5: current branch doesn't match the issue.
  - Its "hard requirement for the user's judgment" exception in **Autonomy**.
  - Indirectly, through `pr`'s questions (see the next bullet).

  Its plan loop leaves `needs user decision` questions in the plan's `## Open Questions`, and
  reports `requires user judgment` fixes (set aside unapplied) only in the loop's final summary,
  so the implementer resolves them silently.
- `skills/pr/SKILL.md` asks the user at four points:
  - No issue found (line 28).
  - No checks documented for a changed area (line 38).
  - The plan has incomplete steps (line 50).
  - Auto-fixable lint failures (line 109).
- `implement-and-review` and `branch-review-loop` prompt on a dirty tree in preflight, while
  `design-review-loop` auto-commits a dirty plan file (its only prompt is for a missing plan
  path). In the
  ship chain the tree is clean when they start only if `ship-issue` Phase 1 step 4 stages
  everything `design` wrote. Today it stages just the plan file, so a `tasks/<slug>_mockups/`
  folder stays untracked and trips the prompt (Implementation Steps, `ship-issue`, fixes this).

## Design

### Shape: modes on existing skills, plus thin entry-point skills

Every behavior change lives in the skill it changes, as a new Phase 0 argument. This is the same
mechanism as the existing round-cap and reviewer-model overrides. The three new skills are thin
wrappers that invoke a skill via the `Skill` tool with a mode appended to their arguments, the
way `implement-and-review` invokes `branch-review-loop`.

```
/autonomous-branch-review-loop [base] ─▶ branch-review-loop   "<args> — autonomous mode"
/autonomous-design-review-loop <plan> ─▶ design-review-loop   "<args> — autonomous mode"
/ship-auto <issue>                    ─▶ ship-issue           "<args> — AFK mode"
     ship-issue (AFK mode)
       ├─▶ design
       ├─▶ autonomous-design-review-loop
       ├─▶ decision pass                    (new, AFK mode only)
       ├─▶ implement-and-review "<plan> — autonomous mode"
       │      └─▶ autonomous-branch-review-loop "<base> — use opus for the reviewer"
       └─▶ pr "AFK mode"
```

There are two distinct terms:

- **Autonomous mode** (loops): no round cap, and trivial issues fixed in-round.
- **AFK mode** (`ship-issue`, `pr`): never prompt the user. Take the stated default instead and
  record it as a decision.

Each wrapper passes through anything else in its `$ARGUMENTS` and relays the invoked skill's
final summary. It adds nothing else.

### Autonomous mode — loop overrides

Each loop gains one `## Autonomous mode` section, placed after Phase 6 and before Notes, listing
its overrides phase by phase. Phase 0 gets one line: autonomous mode is off by default, and when
the invocation requests it, the overrides in that section apply. Default-mode text is not touched.

1. **No round cap.** Phase 0 sets no cap. A caller-specified cap is ignored in this mode.
2. **Stop conditions (Phase 2).** Drop *round cap* and *oscillation/accretion*. Both stop the loop
   while substantive issues are still being raised, which is exactly what this mode is for. Keep:
   - *Clean* and *only trivial* (*nothing fixable*). The loop runs only while substantive issues
     exist, and trivials never extend it.
   - *Non-convergence*. A substantive set that matches an earlier round's means the next round
     will repeat this one. Without a cap, this is the only guard against an endless loop.
   - *Growth* (design loop only). This is the plan-size guard the 1.20.0 convention requires. Its
     budget stays caller-overridable.
   - *Reviewer failure*, unchanged.
3. **Trivial ledger replaces `deferred`.** Phase 0 initializes an empty `trivial_ledger` instead
   of `deferred`. Each entry holds the issue's summary, its location (section, in the design
   loop), and the fixer's one-line report on it — including a report that the fixer declined the
   fix.
4. **Ledger filter (Phase 2, before the stop conditions).** Drop any trivial from this round that
   matches a ledger entry. A match has the same location/section **and** the same subject (the
   same identifier, phrase, or construct), whether the new finding asks to repeat, refine, or
   reverse the earlier edit.
   - When unsure, drop it. A skipped nit costs nothing; a flip-flop costs a commit and a review
     round.
   - A ledgered item re-reported as substantive is still dropped, but recorded: keep its summary
     and location/section for the final summary.
   - Count the dropped items per round for the summary.
   - A substantive finding on a different subject is never dropped just because it shares a
     ledgered location.
5. **Fix trivials in-round (Phase 3).** When a round has substantive issues, the fixer receives
   them **plus** the round's surviving trivials, in the same prompt. Phase 3's pre-fix printed
   list includes the trivials being sent, and the fixer returns one line per issue it was given,
   including any it declined. After the fixer returns, the orchestrator appends every trivial it
   sent to `trivial_ledger`, with the fixer's line.
   Trivials alone never trigger a fix round; that's the *only trivial* stop.
6. **Finalize (Phase 5).** Same shape as today. Its input depends on why the loop stopped:
   - *Only trivial*: the last round's surviving (post-filter) trivials.
   - *Non-convergence* or *growth*: those trivials plus the unresolved substantive issues.
   - *Reviewer failure*: skip Phase 5. This overrides Phase 1's reviewer-failure routing, which
     sends the previous round's trivials to Phase 5; in this mode they are already in
     `trivial_ledger`, fixed or declined in-round.

   Trivials the finalize agent fixes aren't added to the ledger, since nothing reviews after it.
7. **Final summary (Phase 6).** The outcome list drops round cap and oscillation-accretion. Each
   round's note adds how many trivials were fixed and how many ledgered trivials were skipped. It also lists each dropped item that was
   re-reported as substantive, by summary and location/section.

In the design loop, `needs user decision` questions and `requires user judgment:` fixes are set
aside before the trivial partition, exactly as today. A trivial that carries that prefix is never
sent to the fixer, in either mode.

### `implement-and-review` — autonomous mode pass-through

Phase 0 accepts `autonomous mode`. When it's set, Phase 2 invokes `autonomous-branch-review-loop`
instead of `branch-review-loop`, passing `<base> — use opus for the reviewer` (no round cap).
Phase 3's convergence wording lists the stop conditions that the invoked loop can actually report.

### `pr` — AFK mode

Phase 1 accepts `AFK mode`. Each question gets a default instead, and every default taken is
listed in `pr`'s output under `Decisions taken (AFK mode):`.

| Prompt today | AFK-mode default |
|---|---|
| No issue found (line 28) | Open the PR without an issue link. |
| No checks documented for a changed area (line 38) | Run no checks for that area. Say so in the PR body's `## Test plan`. |
| Plan has incomplete steps (line 50) | Leave the plan in `tasks/` and list the incomplete steps in the PR body's `## Summary`. |
| Auto-fixable lint failure (line 109) | Apply the auto-fix, commit it, and re-run the failing checks once. If they still fail, stop as today. |

Failing checks, a diverged remote, and every other existing stop still stop. Stopping isn't
blocking: the skill ends and reports.

### `ship-issue` — AFK mode

Phase 0 accepts `AFK mode`. It applies these overrides, listed in one `## AFK mode` section:

1. **Preflight never asks.**
   - Dirty tree: run `git stash push -u -m "ship-auto: WIP set aside"` instead of asking. This
     keeps unrelated WIP out of the PR, and the user can restore it with `git stash pop`.
   - Branch mismatch: take option (b) — create the issue's feature branch off `<base>`.
   - The **Autonomy** section's "hard requirement for the user's judgment" exception is
     disabled. Instead, take the most conservative option, and note the choice as it is made.
   - The **Autonomous push** reminder is still emitted at the start, without pausing.
2. **Plan loop.** Phase 2 invokes `autonomous-design-review-loop` with the plan path, in place
   of `design-review-loop` with a cap of 10.
3. **Decision pass (new step at the end of Phase 2).** If the loop left any `needs user decision`
   questions or `requires user judgment` fixes, spawn one `Task` agent (`general-purpose`,
   session model) with the plan path and those items. It must:
   - Resolve each one by choosing the most conservative option that still satisfies the issue.
     For a `requires user judgment` fix, that means applying or declining it.
   - Record each resolution as one line in the plan's `## Decisions` section, prefixed `AFK:`,
     and remove each resolved question from `## Open Questions`.
   - Return the lines it wrote.

   The orchestrator commits the plan with the same `-F` protocol as Phase 1 step 4. This settles
   the choices before the implementer would otherwise make them silently, and makes them
   listable.
4. **Implementation.** Phase 3 passes `<plan path> — autonomous mode` to `implement-and-review`.
5. **PR.** Phase 4 passes `AFK mode` to `pr`.
6. **Decisions report (Phase 5).** The final summary leads with a **Decisions taken** list. It
   also runs when the chain hard-stops, listing the decisions taken up to that point. The list is
   gathered from these sources, in this priority order:
   1. The preflight defaults taken: stash and branch choice, plus the stash name so the user can
      restore it, and each conservative-option choice noted in place of a user-judgment stop.
   2. The decision pass's `AFK:` lines.
   3. Every non-clean loop outcome: findings closed by an unreviewed finalize pass, and anything
      left unfixed.
   4. `pr`'s `Decisions taken (AFK mode):` list.
   5. The other `## Decisions` lines the plan gained during the run. Read the plan at whichever
      path it currently has (`tasks/` or `tasks/completed/`, since `pr` moves it), and find the
      added lines with `git diff -M <plan commit>..HEAD` over both paths.

   Cap the list at 10 lines, in that order. If entries were cut, end with a pointer to the plan's
   `## Decisions` section for the full record.

## Implementation Steps

1. `skills/branch-review-loop/SKILL.md`
   - Phase 0: add one line that enables autonomous mode on request, pointing at
     `## Autonomous mode`.
   - Add `## Autonomous mode` with the seven overrides (location in place of section).
   - Notes: add one bullet saying autonomous mode is a shared mechanic and must stay mirrored.
2. `skills/design-review-loop/SKILL.md`: the same three edits. Use section in place of location,
   keep growth as a stop condition, and include the set-aside paragraph.
3. `skills/implement-and-review/SKILL.md`: autonomous-mode pass-through in Phase 0, Phase 2, and
   Phase 3.
4. `skills/pr/SKILL.md`: set `argument-hint` to `[AFK mode]`, AFK-mode argument in Phase 1, the four defaults at their prompt sites (or
   one table that each site references), and the `Decisions taken (AFK mode):` output.
5. `skills/ship-issue/SKILL.md`:
   - Phase 1 step 4 (applies outside AFK mode too): when `design` produced
     `tasks/<slug>_mockups/`, stage that folder by explicit path together with the plan.
   - Phase 0: AFK-mode argument.
   - Add a `## AFK mode` section with the six overrides.
   - Add `Task` to `allowed-tools`, for the decision pass.
6. Create `skills/autonomous-branch-review-loop/SKILL.md`, `skills/autonomous-design-review-loop/SKILL.md`,
   and `skills/ship-auto/SKILL.md`.
   - Frontmatter: `name`, `description`, `argument-hint` (copy each target's), and
     `allowed-tools: Skill`.
   - Body: invoke the target skill via the `Skill` tool with `$ARGUMENTS — <mode>`, and note that
     all behavior lives in the target's mode section. `ship-auto`'s description says it never
     prompts and reports the decisions it took.
7. `README.md`: three rows in the skill table, and one sentence in "How the skills compose".
8. `CLAUDE.md`:
   - Skill count (eight → eleven), the skill list, and three Architecture lines.
   - Extend the near-mirror bullet: autonomous mode is a shared loop mechanic.
   - Extend the `/implement-and-review` bullet with the autonomous-mode pass-through.
   - Extend the `/ship-issue` bullet: AFK mode, the decision pass, and the wrappers holding no
     logic.
9. `.claude-plugin/plugin.json`: bump the version to `1.22.0`. Update the shared description in
   both `plugin.json` and `marketplace.json` to mention autonomous loops and ship-auto. Add a `## [1.22.0]` entry to
   `CHANGELOG.md`.
10. Run `python3 scripts/validate.py`.

## Files to Modify

- `skills/branch-review-loop/SKILL.md`
- `skills/design-review-loop/SKILL.md`
- `skills/implement-and-review/SKILL.md`
- `skills/pr/SKILL.md`
- `skills/ship-issue/SKILL.md`
- `skills/autonomous-branch-review-loop/SKILL.md` (new)
- `skills/autonomous-design-review-loop/SKILL.md` (new)
- `skills/ship-auto/SKILL.md` (new)
- `README.md`, `CLAUDE.md`, `CHANGELOG.md`
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

## Trade-offs

- **Modes plus thin wrappers vs. standalone skill files.** Standalone copies would add two more
  ~300-line near-mirror loops and a near-copy of `ship-issue`. The existing loop pair has already
  drifted when a change landed in only one of them. A Phase 0 argument is the repo's established
  way to vary a skill for a caller, and the wrappers still give the user the requested slash
  commands.
- **Ledger in the orchestrator vs. recording trivial outcomes in the artifact.** Writing them to
  the plan's `## Decisions` would stop flip-flops at the reviewer. But it would flood the plan
  with nits, which feeds the growth stop, and it has no equivalent for code. With the ledger in
  the orchestrator, the stateless reviewer can keep re-reporting a settled nit harmlessly: the
  nit is filtered out, and trivials never keep the loop alive.
- **Stash vs. baseline commit for a dirty tree in AFK mode.** A baseline commit would carry
  unrelated WIP into the PR. A named stash keeps the WIP recoverable and out of the PR.
- **No AFK mode for `implement-and-review` or the loops' preflight.** Their only prompt is the
  dirty-tree check, and in the ship chain the tree is clean when they start once Phase 1 step 4
  stages the mockups folder with the plan.
- **Decision pass vs. leaving open items to the implementer.** If the open items are left, the
  implementer still decides them, but invisibly. The pass makes those decisions explicit,
  committed, and listable at the cost of one agent call.

## Documentation

`README.md` and `CLAUDE.md` as in steps 7–8, and a `CHANGELOG.md` entry for 1.22.0.

## Testing Strategy

The repo has no test harness for skill behavior. Skills are prompts executed by a model, so their
logic can't be called with constructed inputs. `scripts/validate.py` (run in CI) covers the
structural surface:

- The new skills' frontmatter and directory names.
- `Skill` declared in the wrappers' `allowed-tools`.
- `Task` declared in `ship-issue`'s `allowed-tools`.
- README and CLAUDE.md coverage.
- Manifest description sync and the version ↔ CHANGELOG sync.

## Manual Verification

These checks aren't automatable because the behavior emerges from model runs. Breakage (a wrong
stop, a nit flipped back, a prompt during an AFK run) shows up in the final summary, the commit
log, or a visible pause.

1. On a scratch branch with a few deliberate bugs and nits, run
   `/autonomous-branch-review-loop main`. Expected:
   - Round commits include trivial fixes alongside substantive ones.
   - The summary lists, per round, the trivials fixed and the ledgered trivials skipped.
   - The outcome is clean, only trivial, or non-convergence. It's never round cap or accretion.
2. Run `/autonomous-design-review-loop tasks/<some plan>.md`. Expected: the same as step 1, plus
   the plan-size report, with `needs user decision` and `requires user judgment` items surfaced
   but not fixed.
3. In a scratch repo with an open test issue and an uncommitted file, run
   `/ship-auto <issue> — push and open the PR when done` and walk away. Expected:
   - The run never pauses for input.
   - The WIP file is in a stash named `ship-auto: WIP set aside`.
   - The PR exists.
   - The final summary leads with a Decisions taken list that includes the stash.
4. Run `/branch-review-loop main` and `/ship-issue <issue>`. Expected: default behavior is
   unchanged — trivials deferred to the finalize pass, a cap of 5, and the preflight prompts
   still asked.

## Open Questions

- Dropping oscillation/accretion follows "keep looping while important issues are raised". But
  accretion was the guard against a loop manufacturing its own findings (CLAUDE.md, 1.20.0). With
  no cap, only non-convergence (and growth, for plans) can stop such a run short of the user
  interrupting it. Should accretion stay dropped, or stay in autonomous mode as well?
- Should `ship-auto` also post the Decisions taken list as a comment on the PR it opens? An AFK
  user may see the PR before the terminal.
