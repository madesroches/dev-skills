# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Claude Code plugin (`dev-skills`) that provides six slash-command skills for development workflows: `/pr`, `/design`, `/design-review`, `/design-review-loop`, `/branch-review`, and `/branch-review-loop`. There is no build system, no tests, and no dependencies — the repo is purely markdown-based skill definitions.

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
```

Each `SKILL.md` has YAML frontmatter (`name`, `description`, `argument-hint`, `allowed-tools`) followed by the full skill prompt. Skills are self-contained — each file defines the complete behavior for its slash command.

## Key Conventions

- **`tasks/`** holds active design plans; **`tasks/completed/`** holds finished ones. The `/pr` skill moves completed plans automatically.
- `/pr` discovers lint/test commands by reading the *target project's* `CLAUDE.md` (not this one) and cross-referencing `git diff --stat` to run only relevant checks.
- `/design-review` and `/branch-review` both use a **candidate → parallel verification → report** pattern: identify potential issues, verify each against real code using parallel Explore agents, then report only confirmed issues.
- Skills declare their tool allowlists in frontmatter. When editing a skill, keep `allowed-tools` in sync with what the prompt actually uses.
