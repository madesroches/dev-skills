---
name: branch-review
description: Code review the current branch with verified issues only
argument-hint: "[base-branch]"
allowed-tools: Bash(git log *), Bash(git diff *), Bash(git symbolic-ref *), Edit, Read, Glob, Grep, Write, Task
---

# Code Review — Verified Issues Only

Review the current branch against `$ARGUMENTS`. If no base is given, use the repo's default
branch (`git symbolic-ref --short refs/remotes/origin/HEAD`, stripping the `origin/` prefix;
fall back to `main` if no remote HEAD is configured).

## Process

### Phase 1: Gather context

1. `git log --oneline <base>..HEAD` — list commits
2. `git diff <base>...HEAD --stat` — file summary
3. `git diff <base>...HEAD` — full diff (three-dot: diffs from the merge-base, so commits that
   landed on `<base>` after the branch point don't pollute the review)
4. If the file summary includes a plan file under `tasks/` or `tasks/completed/`, read it — that is
   this branch's plan. Its `## Manual Verification` section records which checks were deliberately
   left unautomated, and Phase 2 treats that as settled

### Phase 2: Identify candidate issues

Scan the diff for potential problems:
- Bugs, logic errors, race conditions
- Duplicated patterns that should be extracted
- Missing error handling at system boundaries
- Type safety holes (unsafe casts, type assertions, unchecked conversions)
- Stale or missing dependency declarations (e.g. React hook dependency arrays, cache invalidation keys)
- Security concerns (injection, XSS, secrets)
- API design issues (confusing interfaces, leaky abstractions)
- Performance implications (N+1 queries, repeated work in hot paths, unbounded growth — e.g. unnecessary re-renders in UI code)
- Test coverage gaps (new code without tests, existing tests invalidated by changes) — except
  where the branch's plan file has a `## Manual Verification` entry covering the changed behavior,
  which is a recorded decision not to automate that check. What *is* a candidate for such an
  entry: the diff has moved past it (its command, flag, or expected output no longer matches what
  the code does), the behavior turns out to be reachable by a unit test after all, or its failure
  would be silent (data corruption, auth/permissions, money, migrations, concurrency) — nobody
  notices that class of breakage by running the thing
- Tests that don't earn their cost — tests are not free (CI time, flakiness, fixture and
  maintenance burden), so a heavyweight test has to buy something a cheap one can't. Treat each
  as a candidate: a live DB, real network call, real service, or container-backed test for logic
  a unit test would cover fully; an integration test whose assertions only exercise pure
  functions; a new test that duplicates coverage an existing test already provides; a test that
  asserts its own mocks rather than real behavior; heavyweight fixtures or harnesses added for a
  change that doesn't touch the dependency they exist to exercise. A test that pins a bug seen in
  the wild is **exempt**, down to the tier that actually reproduces that bug
- Project convention violations (naming, patterns, style inconsistent with surrounding code)
- Documentation gaps — public APIs, config options, CLI flags, or behavior changed by the diff
  that existing docs (READMEs, guides) still describe the old way, or new user-facing surface
  with no docs at all
- Suppressed lints introduced by the diff (Rust `#[allow(clippy::...)]` / `#[expect(clippy::...)]`, and equivalent suppressions in other linters) — treat each as a candidate: the underlying lint may be flagging a real concern that should be fixed rather than silenced

For each candidate, write a one-line summary and note which files/lines are involved.

### Phase 3: Verify candidates (parallel)

Launch verification agents in parallel using the Task tool with `subagent_type: "Explore"`.

**Grouping strategy:**
- Group candidates that share the same file(s) into a single agent
- Each agent handles one group of related candidates
- If there are 3 or fewer total candidates, verify them all in a single agent instead of parallelizing

**Each agent prompt must include:**
1. The candidate issue(s) to verify — summary, file paths, and line numbers
2. The relevant section of the diff for context
3. The verification checklist:
   - Can the problematic state actually be reached? Trace callers and data flow.
   - Does the type system, framework, or UI prevent the scenario? Check type constraints, validated inputs, and (in UI code) component props and select options.
   - Is there existing handling elsewhere that covers this case?
   - Is the "missing" code actually unnecessary given the guarantees of the framework or surrounding code?
   - For a documentation candidate: does a relevant doc file exist, does it cover the changed
     area, and does the diff actually make it inaccurate (or introduce user-facing surface it
     should cover)?
   - For a test-cost candidate: ask what the cheap test would fail to catch. Confirm it only if
     the expensive dependency is genuinely unnecessary — the assertions never depend on real
     schema, migration, driver, serialization, wire-format, or transaction behavior — **and** a
     cheaper seam already exists in this repo (an existing fake, in-memory adapter, or unit-test
     fixture pattern for the same area; go read the neighbouring tests to check). Name the
     cheaper test that should replace it. Dismiss it as a false positive when the real dependency
     is itself the thing under test, when the test pins a bug the project actually hit in the wild
     (check the branch's plan, any issue it links, and `git log` for the fix — a regression test
     for a bug that really occurred earns its cost, and stepping it down to a tier that no longer
     reproduces the bug is not a cheaper test but a dead one), or when no cheaper seam exists and
     building one would cost more than the test saves.
   - For a manual-verification candidate: read the plan entry against the diff. Confirm it when
     the entry's command or flag no longer exists or its expected output contradicts what the code
     now does, when the changed behavior is callable with constructed inputs (name the unit test
     that should cover it), or when the failure would be silent. Dismiss it as a false positive
     when the entry still exercises the changed behavior and breakage would be immediately visible
     to the next person who runs the command.
   - For a suppressed lint (e.g. `#[allow(clippy::...)]` / `#[expect(clippy::...)]`): what exactly does that lint flag, and does it point to a real concern in this code? Confirm it only if the suppression hides a genuine problem that should be fixed instead — read the annotated code and judge whether the fix is warranted. Dismiss it as a false positive when the suppression is justified (intentional, idiomatic, or the lint is a genuine false positive here), especially if a nearby comment explains why.
4. Instructions to return a verdict for each candidate: **confirmed** or **false positive**, with a one-line explanation

Launch all agents in a single message so they run concurrently. Collect all results before proceeding.

### Phase 4: Report

Classify each confirmed issue by severity:

- **substantive** — a real bug, logic/race/security/type error, breakage, or missing handling
  that should be fixed
- **trivial** — style, naming, formatting, optional polish, or nitpick

Output a concise list of **confirmed issues only**. For each, report:

- `severity`: substantive or trivial
- `summary`: one line
- `location`: file and line reference
- `why`: what you verified that makes it a real problem
- `fix`: the suggested fix in one sentence

At the end, note how many candidates were dismissed as false positives (no need to list them individually unless the user asks).

This structured format is the skill's output contract: callers that run Phases 1–4
programmatically (e.g. `branch-review-loop`) consume these fields as-is — keep the field names
and severity definitions stable.

### Phase 5: Act on results

If there are confirmed issues, first output the full Phase 4 report so the user sees every
confirmed issue — severity, summary, location, why, and suggested fix — and only then ask whether
they want the fixes applied. Never ask before the report is on screen, and never bury the issue
list inside the question itself.

If yes, apply fixes for all confirmed issues directly in the code. For each fix, explain what you're changing and why before editing.
