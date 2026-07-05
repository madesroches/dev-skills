# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Claude Code plugin (`dev-skills`) that provides seven slash-command skills for development workflows: `/pr`, `/design`, `/design-review`, `/design-review-loop`, `/branch-review`, `/branch-review-loop`, and `/implement-and-review`. There is no build system, no tests, and no dependencies — the repo is purely markdown-based skill definitions.

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
```

Each `SKILL.md` has YAML frontmatter (`name`, `description`, `argument-hint`, `allowed-tools`) followed by the full skill prompt. Skills are self-contained — each file defines the complete behavior for its slash command.

## Key Conventions

- **`tasks/`** holds active design plans; **`tasks/completed/`** holds finished ones. The `/pr` skill moves completed plans automatically.
- `/pr` discovers lint/test commands by reading the *target project's* `CLAUDE.md` (not this one) and cross-referencing `git diff --stat` to run only relevant checks.
- `/design-review` and `/branch-review` both use a **candidate → parallel verification → report** pattern: identify potential issues, verify each against real code using parallel Explore agents, then report only confirmed issues.
- Skills declare their tool allowlists in frontmatter. When editing a skill, keep `allowed-tools` in sync with what the prompt actually uses.
- `/implement-and-review` is a composite skill: it doesn't restate `branch-review-loop`'s logic, it reads that skill's file at its resolved absolute path and follows it directly, overriding only the reviewer's model to `opus`. If `branch-review-loop` changes, this skill inherits the change automatically.
- No skill or subagent in this repo should add `Co-Authored-By` lines or other AI attribution to commits — this is an explicit user requirement, not an omission.
