---
name: autonomous-branch-review-loop
description: Review and fix the current branch with no round cap, fixing trivial issues in-round, until no substantive issues remain
argument-hint: "[base-branch]"
allowed-tools: Skill
---

# Autonomous Branch Review Loop

Invoke the `branch-review-loop` skill via the `Skill` tool, passing `$ARGUMENTS — autonomous mode`.
Pass through anything else in `$ARGUMENTS` unchanged, and relay that skill's final summary.

This skill holds no logic of its own: all behavior (no round cap, the trivial ledger, in-round
trivial fixes) lives in `branch-review-loop`'s `## Autonomous mode` section.
