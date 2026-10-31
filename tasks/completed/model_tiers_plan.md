# Model Tiers and Implement/Review Split Plan

## Overview

Skills name Anthropic models (`sonnet`, `opus`) directly. Those names are really two roles — a
fast tier for mechanical, well-specified work and a strong tier for judgment — and they make the
plugin read as Anthropic-only to anyone running Claude Code against Bedrock, Vertex, or a gateway
that maps the aliases to other models. This plan has each skill that spawns model-specific agents
declare two placeholders, `{{coding}}` and `{{thinking}}`, in one canonical line, and use the
placeholders everywhere else. Brand names then live in exactly that line (plus README/CHANGELOG),
and `scripts/validate.py` enforces it.

The same release splits implementation from review in the ship chain. `implement-and-review`
currently nests `Skill` → `Skill` → `Task` (it loads `branch-review-loop` from inside its own
body), so its ~120 lines of wrapper instructions sit in the orchestrator's context for the whole
review loop. A new `implement` skill takes the implementation half; `ship-issue` then invokes
`implement` and `branch-review-loop` directly, one level each, and `implement-and-review` shrinks
to a thin standalone wrapper over the two. This also makes the tier story cleaner: the coding
tier lives in `implement`, and callers ask each review loop for the thinking tier themselves.

## Current State

Model names are used three ways (grep of `skills/`):

- `model: "sonnet"` for fixer, finalize, implementer, rebase-resolver, and `babysit-pr` fixer
  agents: `skills/branch-review-loop/SKILL.md:45,52,174,232`,
  `skills/design-review-loop/SKILL.md:45,52,187,255`, `skills/implement-and-review/SKILL.md:22,69`,
  `skills/babysit-pr/SKILL.md:23,70,97,132`, `skills/pr/SKILL.md:109`.
- `opus` as a reviewer override requested by composite skills:
  `skills/implement-and-review/SKILL.md:12,26,102-114`, `skills/ship-issue/SKILL.md:75,92-93,190`;
  honored by the loops' Phase 0 (`branch-review-loop:93-95`, `design-review-loop:89-91`) and Roles
  prose (`:41-44`).
- No override: the default reviewer inherits the session model. Not a brand reference; unchanged.

Brand names also appear in the `babysit-pr` frontmatter description (`implement-and-review`'s says
only "a stronger model"), `README.md:15-16,43`, and `ship-issue/SKILL.md:261` (the `babysit-pr`
fixer mention). A grep also finds hits the lists above omit: `babysit-pr:3,11,132`,
`branch-review-loop:47`, `design-review-loop:47`, and `implement-and-review:23,67,102,106,107,114`
(including phase headings such as "Phase 1: Implement (sonnet agent)" and "Review loop (opus)").

`implement-and-review/SKILL.md` holds both halves: Phase 0 preflight (plan check, base branch,
dirty-tree prompt, feature branch, baseline commit, scratch path), Phase 1 implementer agent,
Phase 2 `branch-review-loop` invocation (cap 10, strong reviewer; autonomous variant on request),
Phase 3 summary. `ship-issue` invokes it at `ship-issue/SKILL.md:187` (AFK: `:255`) and describes
it at `:12,30,69-73,92,150,216,284-295`. There is no skill that only implements.

Skills already use `$ARGUMENTS` (e.g. `implement-and-review/SKILL.md:11`), so a `$`-prefixed
placeholder risks colliding with argument substitution.

`scripts/validate.py` has six checks (frontmatter, version/changelog sync, manifest sync,
README/CLAUDE.md coverage, tool declarations, qualified invocations) and no test suite.

## Design

**Tiers.** Two named tiers; the third behavior (inherit) stays "no override".

| Placeholder | Role | Default value passed as `model` |
|---|---|---|
| `{{coding}}` | fixer, finalize, implementer, rebase resolver, CI fixer | `sonnet` |
| `{{thinking}}` | reviewer when a caller requests a stronger one | `opus` |

**Canonical declaration.** One paragraph, byte-identical in every skill that uses a placeholder,
placed directly under the skill's H1 intro. Draft wording:

> **Model tiers.** This skill names models by role. `{{coding}}` is the tier for well-specified,
> mechanical work — pass `model: "sonnet"`. `{{thinking}}` is the tier for judgment — pass
> `model: "opus"`. To run on other models, remap those aliases with Claude Code's
> `ANTHROPIC_DEFAULT_SONNET_MODEL` / `ANTHROPIC_DEFAULT_OPUS_MODEL`, or swap the two quoted
> values for another alias (`sonnet`, `opus`, `haiku`, `fable`) here.

Rest of each skill uses only `{{coding}}` / `{{thinking}}`: `model: "{{coding}}"` becomes
"`model` = `{{coding}}`", and prose like "an `opus` reviewer" becomes "a `{{thinking}}` reviewer".

**Cross-skill requests.** Callers ask for a tier by placeholder name ("use the `{{thinking}}`
tier for the reviewer"); the loop's Phase 0 accepts a tier name or an explicit model and resolves
it through its own declaration. Nothing about how callers hand arguments to loops changes.

**Ship chain tiers (`/ship-auto`, `/ship-issue`).** The chain should design on `{{thinking}}` and
code on `{{coding}}`. Coding already holds: the implementer, fixer, finalize, and resolver agents
are all `{{coding}}`. Design does not: `dev-skills:design` runs through the `Skill` tool in the
main context, so it takes the session model, and `design-review-loop`'s reviewer inherits it.
Wrapping `design` in a `Task` agent is out (its Explore agents would need spawn depth 2). Two
changes:
1. `ship-issue` passes an explicit `{{thinking}}` reviewer request to `design-review-loop` (and to
   `autonomous-design-review-loop` in AFK mode), the same mechanism `implement-and-review` already
   uses for the code reviewer. This works regardless of the session model.
2. `ship-auto` gets `model: opus` in its frontmatter. Per the Claude Code docs a skill's `model`
   applies "for the rest of the current turn", and `/ship-auto` is one autonomous turn, so the
   orchestrator and `design` authoring run on the strong model while every spawned agent is pinned
   to a tier explicitly. Frontmatter cannot hold a placeholder, so `validate.py` allows a model
   alias in the `model:` frontmatter key and nowhere else outside the declaration. `ship-issue`
   (interactive) is not pinned: it respects the user's chosen session model.

**Implement/review split.**
- New `skills/implement/SKILL.md` (`argument-hint: "<path to plan file>"`): the current
  `implement-and-review` Phase 0 (steps 1-6, baseline commit message prefixed `implement:`) and
  Phase 1 moved, minus references to the review phase, with the implementer on `{{coding}}`.
  `autonomous mode` parsing (step 1) stays in the wrapper, and step 2 is trimmed to the base
  branch `implement` needs for its own branch check; callers resolve their own. It does not run
  the review loop. No mode argument: AFK callers already clean the tree before invoking it.
  `implement` ends with a fixed report: on success the commit SHA, a one-line description, the
  checks run, and manual-verification status; on failure a first line beginning `BLOCKED:`.
  Callers detect blockage from that line and reuse the report in their summaries. `allowed-tools`
  are `Read, Write, Bash(git *), Bash(mktemp *), Task, AskUserQuestion`, and the
  `implement-and-review-impl-commit-msg` scratch filename is renamed for `implement`.
- `implement-and-review` becomes a wrapper: confirm the plan path, invoke `dev-skills:implement`,
  stop if its report begins `BLOCKED:` (no separate `git log` confirmation; the report carries the
  SHA), resolve `<base>` the way `implement` does (`git symbolic-ref`, falling back
  to `main`), then invoke `dev-skills:branch-review-loop` with it, a round cap of 10, and a `{{thinking}}` reviewer (`dev-skills:autonomous-branch-review-loop`, no cap, when its
  arguments request `autonomous mode`), then write the combined summary. It keeps its public
  contract; only its internals shrink. Its `allowed-tools` drop what it no longer uses (`Task`,
  `AskUserQuestion`, `Write`, `Bash(mktemp *)`) and keep `Read`, `Skill`, and `Bash(git symbolic-ref *)`.
- `ship-issue` stage 3 becomes two invocations: `dev-skills:implement` with the plan path, then
  `dev-skills:branch-review-loop` (AFK: `dev-skills:autonomous-branch-review-loop`) with `<base>`
  from its own Phase 0, a cap of 10 (none in AFK), and a `{{thinking}}` reviewer. Fail-stop
  conditions are unchanged: a blocked implementer still halts the chain before review. The final
  summary reports the implementer commit and the loop's convergence status exactly as it reports
  `implement-and-review`'s today, and AFK decisions are passed through unchanged.

**Validation (`scripts/validate.py`, new check 7).** For each skill:
1. If the body uses `{{coding}}` or `{{thinking}}`, it contains the canonical declaration verbatim
   (the constant lives in `validate.py`); if it contains the declaration, it uses at least one
   `{{coding}}` / `{{thinking}}` outside the declaration paragraph (as check 2 excludes it).
2. No `sonnet`, `opus`, `haiku`, or `fable` (case-insensitive, word-bounded) appears anywhere in
   the file outside the declaration paragraph and the value of a frontmatter `model:` key.
3. Only `{{coding}}` and `{{thinking}}` exist as `{{...}}` tokens.

The check is a pure function `check_model_tiers(rel, text) -> list[str]` so it is unit-testable.

## Implementation Steps

1. **validate.py**: add the canonical declaration constant and `check_model_tiers`; call it from
   `main` per skill; update the module docstring's check list. Add `scripts/test_validate.py`
   (stdlib `unittest`) covering the new function; run it in `.github/workflows/validate.yml`.
1a. **Split**: create `skills/implement/SKILL.md` from `implement-and-review` Phases 0-1; reduce
   `implement-and-review` to the wrapper described in Design; rewire `ship-issue` stage 3 and its
   AFK variant to call `implement` then the review loop; fix `ship-issue`'s prose and fail-stop
   wording, including the "four sub-skills" count (:67, :84; becomes five), the "Why direct Skill"
   rationale (:73-76), the Phase 3 opening (:188-190), AFK step 4 (:255), the Phase 5 summary
   bullet (:216-217), and the Notes (:284-296); the rationale and Notes are rewritten to describe
   the `implement` plus `branch-review-loop` stack. Strip `Task` and `AskUserQuestion` mentions
   from the wrapper's Roles/Notes prose (no longer in its `allowed-tools`, so `validate.py` would
   flag them), and keep `Skill` out of `implement`'s prose.
2. **Declare** the paragraph in `branch-review-loop`, `design-review-loop`, `implement`,
   `implement-and-review`, `babysit-pr`, `pr`, `ship-issue`. Apply to the two loops identically
   (mirror rule).
3. **Substitute** placeholders in those seven files: grep every `skills/*/SKILL.md` for
   sonnet/opus/haiku/fable and clear every hit (headings and frontmatter included; only the
   `model:` frontmatter value is exempt) rather than working from the Current State line list;
   rewrite the `babysit-pr` description to be neutral.
4. **Loops' Phase 0**: reviewer override text accepts a tier name; examples use
   `{{thinking}}`.
4a. **Ship chain**: `ship-issue` requests a `{{thinking}}` reviewer from its plan loop (both
   modes); add `model: opus` to `ship-auto`'s frontmatter; reword `ship-issue`'s role list.
5. **README / CLAUDE.md**: add `/implement` to the skill table and architecture list, to the
   CLAUDE.md:7 skill-name list, change "twelve" to "thirteen" skills, reword the CLAUDE.md:20
   `implement-and-review` line neutrally as a wrapper over `implement` and `branch-review-loop`,
   neutralize the brand names at CLAUDE.md:42-43 (validate.py does not scan CLAUDE.md), update the `implement-and-review` and `ship-issue` convention
   bullets (the composite now chains `design` → `design-review-loop` → `implement` →
   `branch-review-loop` → `pr`); neutral wording in the skill table; README gets a short "Using other
   models" section (env-var remap first, edit-the-declaration second, with the caveat that prompts
   were tuned on Claude); CLAUDE.md gets a Key Conventions bullet and the check list update.
6. **Release**: bump `plugin.json` to 1.32.0; CHANGELOG entry.
7. Run `python3 scripts/validate.py` and the unit tests.

## Files to Modify

- `scripts/validate.py`, `scripts/test_validate.py` (new), `.github/workflows/validate.yml`
- `skills/implement/SKILL.md` (new)
- `skills/{branch-review-loop,design-review-loop,implement-and-review,babysit-pr,pr,ship-issue}/SKILL.md`
- `skills/ship-auto/SKILL.md` (frontmatter `model:`)
- `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`

## Trade-offs

- **Env vars read at preflight** (`DEV_SKILLS_*_MODEL`): one definition point, but needs `Bash`
  calls in every skill's preflight and new allowlist entries. Rejected for the in-prompt
  declaration, which needs no tooling.
- **Per-skill arguments**: threads through every composite skill and both mirrored loops.
  Rejected.
- **Docs-only env remap, no code change**: leaves "sonnet" meaning "your cheap model" and skills
  reading as Anthropic-only. Kept as the recommended customization path, not the whole solution.
- **`ship-issue` spawns the implementer itself** instead of a new skill: avoids a thirteenth skill
  but restates the implementer's contract inside an orchestrator meant to stay limited. Rejected.
- **Declaration duplicated in seven files**: accepted; `validate.py` keeps it byte-identical, the
  same enforcement pattern as the qualified-invocation check.

## Decisions

- Post-review reversal: `ship-auto` no longer pins `model: opus` in its frontmatter (and `validate.py` has no frontmatter exemption). A hard-coded alias in one skill undercut the brand-free goal; `design` authoring runs on the session model and the README says to start `/ship-auto` on the strong model.
- Placeholder syntax is `{{coding}}` / `{{thinking}}`, not `$coding` / `$thinking`: skills already
  use `$ARGUMENTS`, so `$` tokens risk substitution collisions.
- The declaration states the concrete `model` value to pass, not just a class description: the
  `Task` tool needs a literal value, and a prose-only tier would leave the agent to guess.
- Default reviewer stays "inherit"; no third placeholder.
- Per the docs, the `Task` `model` parameter takes aliases only (`sonnet`/`opus`/`haiku`/`fable`),
  never full IDs, so customization is alias swaps or the `ANTHROPIC_DEFAULT_*_MODEL` remap. Note
  aliases resolve differently per provider (e.g. `opus` is an older version on Foundry).
- `/ship-auto` design-on-thinking is settled by scratch runs (Claude Code 2.1.316): `{{...}}`
  placeholders pass through skill bodies untouched; a skill's `model:` pin carries into skills it
  invokes within the same turn; an alias the provider cannot serve fails with `model_not_found` and
  is not retried (the README "Using other models" section must say every alias in use has to
  resolve to a servable model).
## Documentation

- `README.md`: neutral skill table with `/implement` added; revised `ship-issue` composition line;
  new "Using other models" section.
- `CLAUDE.md`: Key Conventions bullet on model tiers; validate.py check list.
- `CHANGELOG.md`: 1.32.0 entry.

## Testing Strategy

- Unit tests (`scripts/test_validate.py`) for `check_model_tiers` with constructed skill text:
  clean file passes; placeholder without declaration fails; declaration without placeholder fails;
  declaration with altered wording fails; brand name in body fails; brand name in frontmatter
  fails; brand name inside the declaration passes; brand alias as the value of a frontmatter `model:` key
  passes; unknown `{{x}}` token fails.
- CI: the existing validate workflow runs `validate.py` against the real repo (catches a skill
  that drifted) and now runs the unit tests.
- Existing checks stay without unit tests; retrofitting them is out of scope.

## Manual Verification

All entries depend on live model routing and are not automated.

0. Run `/dev-skills:implement` alone on a tiny plan from a clean tree on `main`: confirm it creates
   the feature branch, commits once, and does not start a review loop.
1. In a scratch session, run `/dev-skills:implement-and-review` (or `/dev-skills:babysit-pr`) on a
   small plan and confirm the spawned agents use the aliases from the declaration, and that the
   implementer commit is followed by the review loop.
2. Start a session on a cheap model, run `/ship-auto` on a tiny issue, and confirm the plan was
   authored and reviewed on the strong model while the implementer ran on the coding model.
3. Set `ANTHROPIC_DEFAULT_SONNET_MODEL` to a different model ID and confirm the fixer agent runs
   on it.
