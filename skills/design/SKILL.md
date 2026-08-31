---
name: design
description: Research and write a design plan to tasks/ folder
argument-hint: "<feature description, issue link, or context>"
allowed-tools: Read, Glob, Grep, Bash(git log *), Bash(git diff *), Bash(git show *), Bash(ls *), Bash(gh issue view *), WebFetch, WebSearch, Write, Edit, Task
---

# Design — Research and Write a Plan

Create a design plan for the feature or task described in `$ARGUMENTS` and write it to a markdown file in the `tasks/` folder.

**This skill produces a plan document only. Do NOT write any implementation code** — the one exception is standalone HTML/CSS mockups (Phase 4), which are throwaway visual references, not part of the implementation.

## Process

### Phase 1: Understand the Request

Parse `$ARGUMENTS` to identify:
- Feature description or problem statement
- Issue links (fetch with `gh issue view` or WebFetch if provided)
- Any constraints or preferences mentioned

Summarize the goal in one sentence before proceeding.

### Phase 2: Research the Codebase

Explore the codebase to understand the relevant architecture:

1. Identify affected files, modules, and interfaces
2. Understand existing patterns in neighboring code
3. Check for related completed plans in `tasks/` and `tasks/completed/` for precedent
4. Note any existing utilities, types, or abstractions that should be reused
5. Check for documentation in the project that covers the affected area and note what needs updating
6. Use Task tool with Explore agents for broad searches when needed

### Phase 3: Research External Dependencies (if needed)

If the feature requires new libraries, APIs, or external integrations:
- Search for candidate libraries and evaluate them
- Check compatibility with existing stack
- Note version constraints and bundle size implications

### Phase 4: Build UI Mockups (when the feature has a strong UX/UI component)

Skip this phase entirely for backend-only, API-only, CLI-only, or infra work with no user-facing visual surface. If the feature involves new screens, significant layout changes, new components, or a visual redesign, build mockups before writing the plan:

1. Research the application's existing visual style: find its stylesheets, design tokens/theme files, component templates, fonts, color palette, spacing scale, and the framework/component library in use (e.g., Tailwind config, CSS variables, a component library's theme). The mockup should read as "this app," not a generic template.
2. Write one self-contained HTML file per option to `tasks/<slug>_mockups/` (e.g., `tasks/<slug>_mockups/option-a-sidebar-nav.html`). Each file must:
   - Be fully self-contained — inline `<style>`, no external CDN or build step — so it opens directly in a browser with no setup
   - Mimic the app's real fonts, colors, spacing, and component conventions as closely as you can determine from Phase 2's research
   - Use realistic sample content, not lorem ipsum
   - Cover only the states that matter to the design decision (e.g., empty vs. populated) — don't over-build
3. If there are multiple reasonable design directions (different layouts, navigation patterns, information density, etc.), build 2-3 distinct options rather than committing to one, with descriptive filenames and a one-line trade-off note for each.
4. These are local files for the user to open in a browser — do NOT use the Artifact tool to publish them.

### Phase 5: Write the Plan

Write a markdown file to `tasks/<slug>_plan.md` where `<slug>` is a short snake_case name derived from the feature.

The plan should include these sections (adapt as needed — small tasks need less detail):

```markdown
# <Title> Plan

## Overview
One paragraph: what this does and why.

## Current State
How things work today. Include relevant code paths and file references.

## Design
Technical approach. Include:
- Data structures / type changes
- API or interface changes
- Key algorithms or logic
- Architecture diagrams (ascii) if helpful

## Mockups
Only if Phase 4 produced any. List each mockup file's path with a one-line description, and the trade-off between options if there was more than one.

## Implementation Steps
Ordered list of concrete steps. Group into phases for larger tasks.
Each step should reference specific files to modify or create.

## Files to Modify
Quick reference list of files that will be touched.

## Trade-offs
What alternatives were considered and why this approach was chosen.

## Decisions
One line per settled choice, accepted risk, or declined alternative — the record that stops a
settled question from being re-argued later. Add a line here instead of writing a paragraph of
defense into the section the decision touches.

## Documentation
Which project documentation pages need to be created or updated.

## Testing Strategy
How to verify the implementation works.

## Open Questions
Anything that needs clarification before implementation.
```

Omit sections that don't apply. Add sections that are needed (e.g., Migration, Security, Performance, Dependencies).

### Phase 6: Present the Plan

After writing the file, output:
- The file path
- Paths to any mockup files produced in Phase 4
- A brief summary of the approach
- Any open questions that need user input before implementation

## Guidelines

- Reference specific file paths and line numbers when discussing current state
- Keep the plan actionable — someone should be able to implement it from the document alone
- Look at existing plans in `tasks/` and `tasks/completed/` to match the project's level of detail
- Prefer reusing existing patterns over inventing new ones
- Don't over-specify implementation details that are obvious from context
- Say each thing once: state a rationale in the section that owns it, not again in every section
  that touches it. A plan carrying what the goal doesn't need is as defective as one missing what
  it does
- Keep in mind the open/closed principle
- Keep in mind the DRY principle
- DO NOT write any implementation code — only the plan document and, when Phase 4 applies, standalone HTML mockups
- Never use the Artifact tool for mockups — they are local files the user opens directly in a browser
