---
name: design-review
description: Review a design plan document with verified issues only
argument-hint: "<path to plan file>"
allowed-tools: Read, Glob, Grep, Bash(git log *), Bash(git diff *), Bash(git show *), Bash(ls *), Edit, Write, Task
---

# Design Review — Verified Issues Only

Review the design plan at `$ARGUMENTS`.

## Process

### Phase 1: Gather context

1. Read the plan file
2. Read all source files referenced in the plan to understand current state
3. Check `tasks/` and `tasks/completed/` for related plans that establish precedent

### Phase 2: Identify candidate issues

A plan can fail in two directions: missing what the goal needs, and carrying what it does not.
Scan for both, explicitly and separately — once for gaps (the categories below), and once for
excess. Excess candidates include: rationale argued more than once; defenses of decisions nobody
in the codebase or the plan contests; justification an order of magnitude longer than the
instruction it supports; work items (files, steps, tests) the goal does not require. **A finding
whose fix is a deletion is a finding** — report it like any other, naming exactly the lines or
section to delete.

If the plan has a `## Decisions` section (one line per settled choice, accepted risk, or declined
alternative), treat its entries as settled: do not raise a candidate that re-argues a listed
decision unless the codebase makes it factually wrong. Inline prose that defends a decision at
paragraph length is itself an excess candidate — the fix is a one-line entry in `## Decisions`
replacing the paragraph.

Gap candidates — scan the plan for these potential problems:
- **Unresolved open questions** — every entry in the plan's `## Open Questions` section, plus any
  inline `TBD` / `TODO` / "decide later" markers. Treat each as a candidate to **resolve**, not
  merely to flag: most open questions a plan raises are answerable from the codebase itself — an
  existing pattern, interface, or precedent in `tasks/completed/` usually settles them. These are
  candidates like any other and go through Phase 3 verification, where the agent investigates and
  proposes a concrete answer.
- **Incorrect assumptions** about existing code (wrong file paths, misunderstood interfaces, stale references)
- **Missing steps** — changes that would be needed but aren't listed (e.g., updating imports, adding exports, migrations)
- **Ordering errors** — steps that depend on something introduced in a later step
- **Contradictions** — the plan says one thing in one section and something different elsewhere
- **Breaking changes** not accounted for — callers, tests, or dependents that would break
- **Over-engineering** — unnecessary abstractions, premature generalization, solving problems that don't exist
- **Under-specification** — critical decisions left vague that will block implementation
- **Pattern violations** — approaches that conflict with established codebase conventions
- **Type safety gaps** — proposed interfaces that lose type information or require unsafe casts
- **Missing error handling** at system boundaries
- **Test strategy gaps** — untestable designs, missing edge cases, no integration coverage where
  components genuinely interact
- **Test cost not earned** — tests are not free (CI time, flakiness, fixture and maintenance
  burden), so weigh what each test the plan proposes buys against what it costs. Treat as a
  candidate: a live-DB, real-service, network, or container-backed test for logic a unit test
  would cover fully; an end-to-end test standing in for a cheap assertion on a pure function; a
  test plan that duplicates coverage the existing suite already has; new heavyweight fixtures or
  harnesses for a change that doesn't touch the dependency they exist to exercise
- **Performance concerns** — N+1 queries, unnecessary re-renders, unbounded data structures
- **New dependencies** — every third-party package, library, or tool the plan proposes adding. Treat
  each as a candidate to scrutinize on two axes: **value** (does it earn its place, or could existing
  dependencies or a small amount of first-party code do the job?) and **version** (does the plan pin
  the latest stable release, or a stale/outdated one?)
- **Documentation gaps** — public APIs, config options, or architectural decisions introduced by the plan that lack corresponding docs; existing docs (READMEs, guides) that reference affected areas and would become stale

For each candidate, write a one-line summary and note which plan section is involved.

### Phase 3: Verify candidates (parallel)

Launch verification agents in parallel using the Task tool with `subagent_type: "Explore"`.

**Grouping strategy:**
- Group candidates that relate to the same area of the codebase into a single agent
- Each agent handles one group of related candidates
- If there are 3 or fewer total candidates, verify them all in a single agent instead of parallelizing

**Each agent prompt must include:**
1. The candidate issue(s) to verify — summary and which plan section is involved
2. The relevant excerpt from the plan for context
3. The verification checklist:
   - Read the actual source files referenced — does the code match what the plan assumes?
   - Are the interfaces, types, and function signatures as the plan describes?
   - Does the proposed change actually conflict with existing code, or does it fit cleanly?
   - Is the "missing step" truly missing, or is it handled implicitly by existing code or tooling?
   - Is the "over-engineering" concern valid — does the complexity serve a real need evident in
     the codebase, or is it generalization the goal never asks for?
   - Are there existing patterns or utilities the plan overlooks that would simplify or invalidate a step?
   - For excess candidates: confirm the passage restates or defends rather than instructs —
     deleting it must remove no implementation step, no ordering constraint, and no recorded
     decision. Confirmed means naming exactly the lines or section to delete. For a work item
     (file, step, test), confirmed means the goal is still met without it.
   - For test-cost candidates: read the repo's existing tests for this area — is there already a
     cheaper seam (a fake, in-memory adapter, or unit-test fixture pattern) the plan overlooks?
     Ask what the cheap test could not catch, and confirm only when the plan's expensive test
     buys nothing the cheap one wouldn't; name the cheaper test that should replace it. Dismiss
     it when the real dependency (schema, migration, driver, wire format, transaction semantics)
     is itself what needs verifying, or when no cheaper seam exists and building one would cost
     more than the test saves.
   - For documentation candidates: does a relevant doc file exist? Does it cover the area being changed? Would it become inaccurate if the plan were implemented as written?
   - For new-dependency candidates: confirm the package is actually new (not already a
     direct or transitive dependency). Weigh whether it brings enough value to justify the added
     surface area, or whether an existing dependency or modest first-party code would suffice. Look
     up the latest stable version from the authoritative source (e.g. `npm view <pkg> version`,
     `pip index versions <pkg>`, `cargo search`, or the package registry via WebFetch) and compare it
     to the version the plan proposes — flag if it's outdated or unpinned. These lookups are
     **best-effort**: if the command is unavailable or blocked by the permission layer, do not
     stall waiting on it — return the verdict with the version marked *unverified* instead, so
     an autonomous caller (e.g. a review loop) is never blocked on a network lookup.
   - For open-question candidates: search the codebase for the answer — an existing pattern, interface, type, or precedent that determines it. Return a **concrete resolution** when the code settles it. Only when the question is a genuine product/policy decision the code cannot answer (e.g. a UX choice, a business rule) should it be left for the user — say so explicitly.
4. Instructions to return a verdict for each candidate: **confirmed** or **false positive**, with a one-line explanation. For open-question candidates the verdict is instead **resolved** (with the concrete answer the code supports) or **needs user decision** (with why the codebase can't settle it).

Launch all agents in a single message so they run concurrently. Collect all results before proceeding.

### Phase 4: Report

Classify each confirmed issue by severity:

- **substantive** — a real design flaw, ambiguity, or correctness/ordering/breakage problem that
  should be fixed, **or** verified excess whose fix is deleting a work item or a section-scale
  block of prose
- **trivial** — wording, formatting, optional polish, or nitpick

Output a concise list of **confirmed issues only**. For each, report:

- `severity`: substantive or trivial
- `summary`: one line
- `section`: which plan section is involved
- `why`: what you verified against the code that makes it a real problem
- `fix`: the suggested fix in one sentence

For **resolved open questions**, report each as a confirmed **substantive** issue whose `fix` is:
fold the concrete answer into the relevant plan section and remove the item from
`## Open Questions`. An open question that the code answers is a real, fixable gap — surface it so
it gets closed, not left lingering. For a question that genuinely **needs a user decision**, report
it in its own category labeled `needs user decision` (with `section` and why the codebase can't
settle it) — it carries no severity, is never a fixable issue, and stays in `## Open Questions`
for the user.

A confirmed issue whose only fix **introduces new design surface** — a new name, sentinel,
mechanism, or convention the plan does not already contain, as opposed to correcting the plan to
match the codebase or the goal — is still reported as confirmed, but its `fix` is prefixed with
`requires user judgment:` so an autonomous caller surfaces it for the user instead of applying it.
Correcting the plan to match what the codebase already does is never "new design surface"; naming
something the codebase has no name for is.

At the end, note how many candidates were dismissed as false positives (no need to list them individually unless the user asks).

This structured format is the skill's output contract: callers that run Phases 1–4
programmatically (e.g. `design-review-loop`) consume these fields, the `needs user decision`
category, and the `requires user judgment:` fix prefix as-is — keep the field names, severity
definitions, and that prefix stable.

### Phase 5: Act on results

If there are confirmed issues, first output the full Phase 4 report so the user sees every
confirmed issue — severity, summary, section, why, and suggested fix, plus any `needs user
decision` questions — and only then ask whether they want the fixes applied. Never ask before the
report is on screen, and never bury the issue list inside the question itself.

If yes, apply fixes directly in the plan file for all confirmed issues. For each fix, explain what you're changing and why before editing.
