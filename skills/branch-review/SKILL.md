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
- Test coverage gaps (new code without tests, existing tests invalidated by changes)
- Project convention violations (naming, patterns, style inconsistent with surrounding code)
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
   - For a suppressed lint (e.g. `#[allow(clippy::...)]` / `#[expect(clippy::...)]`): what exactly does that lint flag, and does it point to a real concern in this code? Confirm it only if the suppression hides a genuine problem that should be fixed instead — read the annotated code and judge whether the fix is warranted. Dismiss it as a false positive when the suppression is justified (intentional, idiomatic, or the lint is a genuine false positive here), especially if a nearby comment explains why.
4. Instructions to return a verdict for each candidate: **confirmed** or **false positive**, with a one-line explanation

Launch all agents in a single message so they run concurrently. Collect all results before proceeding.

### Phase 4: Report

Output a concise list of **confirmed issues only**. For each:
- One-line summary
- File and line reference
- Why it's a real problem (what you verified)

At the end, note how many candidates were dismissed as false positives (no need to list them individually unless the user asks).

### Phase 5: Act on results

If there are confirmed issues, ask the user whether they want the fixes applied.

If yes, apply fixes for all confirmed issues directly in the code. For each fix, explain what you're changing and why before editing.
