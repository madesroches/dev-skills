# ship-issue: Accept an Existing Plan File Plan

**GitHub Issue**: https://github.com/madesroches/dev-skills/issues/20

## Overview
`/ship-issue` and `/ship-auto` stop at Phase 0 unless given an issue reference. Let them also take a path to an existing plan file, skipping the issue fetch and the `design` stage and starting at plan hardening (Phase 2), with an optional `start at implementation` hint to skip hardening too.

## Current State
- `skills/ship-issue/SKILL.md` Phase 0 step 1 requires an issue reference; steps 2, 5, 7 and Phases 1, 4 assume an issue number/title/url (branch slug, plan commit subject, `**GitHub Issue**:` line).
- AFK mode (`## AFK mode`) commits the decision pass with subject `Record AFK decisions for #<number>`.
- `skills/ship-auto/SKILL.md` passes `$ARGUMENTS — AFK mode` through unchanged, so it needs no logic change.
- `skills/pr/SKILL.md` already opens a PR without an issue link when none is found (Phase 1 table).

## Design
Add an **Input resolution** step to Phase 0 step 1, after stripping the `— AFK mode` text and any push instruction:
1. If the remaining text contains a path to an existing file (`tasks/*.md`, checked with a file-exists test), it is **plan mode**: `<plan path>` = that file. Any remaining text is a stage hint.
2. Else if it looks like an issue reference, **issue mode** — behavior exactly as today.
3. Else (bare/unrecognized): stop with a message naming both accepted forms. Do not scan `tasks/`.

Stage hints (plan mode only): `start at plan hardening` (default) and `start at implementation` (skip Phase 2 and the AFK decision pass; the plan is assumed hardened). Unrecognized hint text is ignored.

Plan-mode overrides of later steps:
- **Phase 0 step 2**: skip `gh issue view`. `<title>` = the plan's first `# ` heading with a trailing ` Plan` removed; no number/url.
- **Step 5 branch slug**: derived from the plan filename (basename, `_plan.md`/`.md` stripped, `_` → `-`, same slugging rules). The "branch name contains the issue number" check becomes "branch name contains the slug"; AFK branch mismatch still takes option (b).
- **Step 7**: the commit message scratch path is only needed if a commit happens; unchanged.
- **Phase 1** is skipped entirely (no `design`, no `**GitHub Issue**:` injection). If the plan file is untracked or modified, commit it with the Phase 1 step 4 protocol, subject `Add design plan: <title>` (≤ 72 chars); otherwise nothing to commit. (An untracked plan would otherwise trip the dirty-tree check in downstream skills.) In the dirty-tree check of step 4, the plan file itself is not "unrelated WIP" and is excluded from the stash/prompt.
- **Commit subjects**: wherever a subject uses `#<number>`, plan mode uses `<title>` (AFK decision pass: `Record AFK decisions for <title>`).
- **Phase 4/5**: `pr` finds no issue link and opens without one; the summary reports the plan path instead of the issue.

Mode handling: the AFK-mode text is stripped first, so a plan path is never mistaken for an issue.

Also update `argument-hint` to `"<issue url or number | plan path> [start at plan hardening|implementation]"` and the first line of `skills/ship-auto/SKILL.md`'s description is unchanged except mentioning plan files if the manifest description sync allows (check `scripts/validate.py`).

## Implementation Steps
1. Edit `skills/ship-issue/SKILL.md`: intro paragraph, `argument-hint`, Phase 0 step 1 (input resolution), steps 2/4/5, Phase 1 skip, Phase 2 hint skip, Phase 5 summary, and a new `## Plan mode` section holding the overrides above (mirroring how `## AFK mode` is structured); AFK mode item 3's commit subject references plan mode's `<title>`.
2. Edit `skills/ship-auto/SKILL.md` only if its description/argument-hint should mention plan paths (no logic).
3. Update `README.md` (skill table rows for `/ship-issue` and `/ship-auto`) and `CLAUDE.md` (the `/ship-issue` convention bullet: plan-mode input).
4. Bump version to 1.34.0 in `.claude-plugin/plugin.json` (and any other manifest carrying it) and add a `CHANGELOG.md` entry dated 2026-11-14.
5. Run `python3 scripts/validate.py` and `python3 scripts/test_validate.py`.

## Files to Modify
- `skills/ship-issue/SKILL.md`
- `skills/ship-auto/SKILL.md` (argument-hint only, if any)
- `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json` (and any manifest `validate.py` syncs)

## Trade-offs
- Auto-discovering a single active plan in `tasks/` for bare invocations was rejected: guessing which plan to ship is the kind of silent choice the chain avoids.
- A separate `ship-plan` skill was rejected: it would duplicate the chain; a mode section follows the existing AFK-mode pattern.

## Testing Strategy
Skills are markdown with no unit-testable logic. `scripts/validate.py` and `scripts/test_validate.py` cover frontmatter, version/CHANGELOG sync, README/CLAUDE.md coverage and allowed-tools. If the new text uses a distinctively-named tool, add it to `allowed-tools` (e.g. `Bash(test *)` if a file-exists check is run via shell; otherwise use `Read`).

## Manual Verification
- Run `/ship-issue <issue number>` on a throwaway issue: behavior is unchanged. Not automated: it drives a live GitHub repo and a full agent chain.
- Run `/ship-auto tasks/<plan>.md`: it starts at hardening with no prompt, no issue link, and a branch named from the plan filename.

## Open Questions
None.
