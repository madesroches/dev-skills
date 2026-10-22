---
name: ship-auto
description: Take a GitHub issue from design to a pull request without ever prompting, then report the decisions taken on your behalf
argument-hint: "<issue url or number>"
allowed-tools: Skill
---

# Ship Auto

Invoke the `ship-issue` skill via the `Skill` tool, passing `$ARGUMENTS — AFK mode`. Pass through
anything else in `$ARGUMENTS` (such as a push instruction) unchanged, and relay that skill's final
summary, including its **Decisions taken** list.

This skill holds no logic of its own: all behavior (never prompting, taking recorded defaults,
the decision pass, the decisions report) lives in `ship-issue`'s `## AFK mode` section.
