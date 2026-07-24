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
- The structured issue format — `severity`/`summary`/`location`(or `section`)/`why`/`fix`, plus `design-review`'s `needs user decision` category — is defined **once**, in `branch-review`/`design-review` Phase 4, as the skill's output contract. The loop skills consume it by reference; never restate field names or severity definitions in a caller.
- `branch-review-loop` and `design-review-loop` are deliberate near-mirrors. Any change to shared loop mechanics (preflight, stop conditions, commit protocol, roles, model overrides) must be applied to both files — they have drifted before when a feature landed in only one.
- Skills declare their tool allowlists in frontmatter. When editing a skill, keep `allowed-tools` in sync with what the prompt actually uses.
- `/implement-and-review` is a composite skill: it doesn't restate `branch-review-loop`'s logic, it invokes that skill directly via the `Skill` tool, passing the base branch, a round cap of 10 (vs. the loop's default 5), and a request to use `opus` for the reviewer — all arguments `branch-review-loop`'s own Phase 0 natively supports, not a deviation from its process. It also appends its own Phase 3 finalize pass, with no counterpart in the loop, that fixes anything the loop left unresolved (trivial issues, or substantive ones left open by a non-clean stop) and commits. If `branch-review-loop` changes, this skill inherits the change automatically since nothing is restated.
- `/ship-issue` is a composite skill that, unlike `/implement-and-review`, needs **no deviation** from the skills it chains, so it composes by invoking each one **directly via the `Skill` tool** (`design` → `design-review-loop` → `implement-and-review` → `pr`) rather than reading their files as text. Its own work is limited to preflight (fetch the issue, create the feature branch up front so all downstream commits land on it), committing the plan once, and injecting a `**GitHub Issue**:` line into the plan so `/pr` can auto-link the issue. Because the final push (which lets CI run) can be gated by the permission layer when a repo's CLAUDE.md requires an explicit push instruction, its Phase 0 reminds the user up front — when the invocation carries no explicit push instruction — to re-invoke with one for a fully autonomous run; it does not pause, and the push simply stalls at `/pr` if left ungated. It fail-stops between stages (no plan produced, implementer blocked, or `/pr` checks failing) and inherits any sub-skill change automatically.
- No skill or subagent in this repo should add `Co-Authored-By` lines or other AI attribution to commits — this is an explicit user requirement, not an omission.
