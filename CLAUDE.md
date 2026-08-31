# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Claude Code plugin (`dev-skills`) that provides eight slash-command skills for development workflows: `/pr`, `/design`, `/design-review`, `/design-review-loop`, `/branch-review`, `/branch-review-loop`, `/implement-and-review`, and `/ship-issue`. There is no build system and no dependencies — the repo is purely markdown-based skill definitions. The one piece of automation is `scripts/validate.py` (stdlib Python, run by `.github/workflows/validate.yml` on every push/PR), which checks skill frontmatter, plugin-version ↔ CHANGELOG sync, manifest description sync, README/CLAUDE.md skill coverage, and that distinctively-named tools used in a skill body are declared in its `allowed-tools`. Run it after any structural change.

## Architecture

```
.claude-plugin/plugin.json   — plugin manifest (name, version, description)
skills/
  pr/SKILL.md                — lint/test runner + PR creation workflow
  design/SKILL.md            — codebase research → design plan writer
  design-review/SKILL.md     — plan reviewer with parallel verification agents
  design-review-loop/SKILL.md — iterative review→fix loop wrapping design-review until convergence
  branch-review/SKILL.md     — branch diff reviewer with parallel verification agents
  branch-review-loop/SKILL.md — iterative review→fix loop wrapping branch-review until convergence
  implement-and-review/SKILL.md — implements a plan (sonnet), commits, then runs branch-review-loop (opus) on the result
  ship-issue/SKILL.md          — chains design → design-review-loop → implement-and-review → pr for a GitHub issue
```

Each `SKILL.md` has YAML frontmatter (`name`, `description`, `argument-hint`, `allowed-tools`) followed by the full skill prompt. Skills are self-contained — each file defines the complete behavior for its slash command.

## Key Conventions

- **`tasks/`** holds active design plans; **`tasks/completed/`** holds finished ones. The `/pr` skill moves completed plans automatically.
- `/pr` discovers lint/test commands by reading the *target project's* `CLAUDE.md` (not this one) and cross-referencing `git diff --stat` to run only relevant checks.
- `/design-review` and `/branch-review` both use a **candidate → parallel verification → report** pattern: identify potential issues, verify each against real code using parallel Explore agents, then report only confirmed issues.
- The structured issue format — `severity`/`summary`/`location`(or `section`)/`why`/`fix`, plus `design-review`'s `needs user decision` category and its `requires user judgment:` fix prefix — is defined **once**, in `branch-review`/`design-review` Phase 4, as the skill's output contract. The loop skills consume it by reference; never restate field names or severity definitions in a caller.
- **Plan review is symmetric by design (1.20.0).** `design-review` scans for excess as well as gaps, verified excess is substantive when its fix deletes a work item or a section-scale block (not trivial), and `design-review-loop` tracks plan size and stops on monotonic growth past a caller-overridable budget. This exists because an earlier version drove plans into overdesign: every gap-shaped category has an additive fix, the fixer's contract makes insertion its only compliant move, and each addition creates the next round's consistency finding. Do not reintroduce a gaps-only category list, downgrade such deletion findings to trivial, or drop the size bookkeeping.
- The `## Decisions` section (one line per outcome settled after authoring — a review finding accepted, a user call, an accepted risk; `## Trade-offs` keeps the authoring-time comparison) is a cross-skill convention: `design` emits it, `design-review` treats its entries as settled, and the loop's fixer records decisions there instead of adding defensive prose. Because the reviewer is stateless, it is the only cheap channel for a decision made *against* a finding — without it, every rejected or reverted fix costs a paragraph of scar tissue.
- `branch-review-loop` and `design-review-loop` are deliberate near-mirrors. Any change to shared loop mechanics (preflight, stop conditions, commit protocol, roles, model overrides, finalize pass) must be applied to both files — they have drifted before when a feature landed in only one. The one **deliberate** divergence is `design-review-loop`'s growth stop condition and its plan-size bookkeeping — diff size is not the analogous signal for code; both files' Notes record the divergence.
- Skills declare their tool allowlists in frontmatter. When editing a skill, keep `allowed-tools` in sync with what the prompt actually uses.
- Both loop skills end with a **finalize pass** (their Phase 5): after the loop stops, a single `sonnet` agent fixes everything left over — the trivial issues the loop skips each round, plus any substantive issues still open if the loop stopped on cap/non-convergence/oscillation-accretion/growth — and the orchestrator commits it using the same protocol as a round commit. It is deliberately *not* re-reviewed, and `design-review-loop` never sends `needs user decision` questions or `requires user judgment` fixes to it. When the loop stopped on cap/non-convergence/accretion/growth the leftovers are *not* the least consequential ones left, so both loops must say so in their final summary. The guarantee "no known open issues on hand-back" belongs to the loops; callers must not re-implement it.
- `/implement-and-review` is a composite skill: it doesn't restate `branch-review-loop`'s logic, it invokes that skill directly via the `Skill` tool, passing the base branch, a round cap of 10 (vs. the loop's default 5), and a request to use `opus` for the reviewer — all arguments `branch-review-loop`'s own Phase 0 natively supports, not a deviation from its process. It has **no** deviation phase of its own: cleaning up the loop's leftovers is the loop's own finalize pass (it used to be this skill's Phase 3, removed in 1.16.0). If `branch-review-loop` changes, this skill inherits the change automatically since nothing is restated.
- `/ship-issue` is a composite skill that, unlike `/implement-and-review`, needs **no deviation** from the skills it chains, so it composes by invoking each one **directly via the `Skill` tool** (`design` → `design-review-loop` → `implement-and-review` → `pr`) rather than reading their files as text. Its own work is limited to preflight (fetch the issue, create the feature branch up front so all downstream commits land on it), committing the plan once, and injecting a `**GitHub Issue**:` line into the plan so `/pr` can auto-link the issue. Because the final push (which lets CI run) can be gated by the permission layer when a repo's CLAUDE.md requires an explicit push instruction, its Phase 0 reminds the user up front — when the invocation carries no explicit push instruction — to re-invoke with one for a fully autonomous run; it does not pause, and the push simply stalls at `/pr` if left ungated. It fail-stops between stages (no plan produced, implementer blocked, or `/pr` checks failing) and inherits any sub-skill change automatically.
- No skill or subagent in this repo should add `Co-Authored-By` lines or other AI attribution to commits — this is an explicit user requirement, not an omission.
