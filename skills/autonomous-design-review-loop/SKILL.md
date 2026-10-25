---
name: autonomous-design-review-loop
description: Review and fix a design plan with no round cap, each substantive finding's severity challenged, and trivial issues fixed in-round, until no substantive issues remain
argument-hint: "<path to plan file>"
allowed-tools: Skill
---

# Autonomous Design Review Loop

Invoke the `dev-skills:design-review-loop` skill via the `Skill` tool, passing `$ARGUMENTS — autonomous mode`.
Pass through anything else in `$ARGUMENTS` unchanged, and relay that skill's final summary.

This skill holds no logic of its own: all behavior (no round cap, the severity challenge, the trivial
ledger, in-round trivial fixes) lives in `design-review-loop`'s `## Autonomous mode` section.
