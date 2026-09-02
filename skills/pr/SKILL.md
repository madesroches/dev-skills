---
name: pr
description: Run lints/tests, finalize plan file, and create a pull request
argument-hint: ""
allowed-tools: Bash(git *), Bash(gh *), Bash(mv *), Bash(mkdir *), Bash(ls *), Bash(mktemp *), Read, Glob, Grep, Edit, Write, Task, AskUserQuestion
---

# Pull Request — Lint, Test, and Submit

Create a pull request for the current branch after running lints/tests and finalizing any associated plan file.

## Process

### Phase 1: Gather Context

1. `git branch --show-current` — identify the current branch
2. Resolve the base branch: `git symbolic-ref --short refs/remotes/origin/HEAD`, stripping the
   `origin/` prefix; if that fails (no remote HEAD configured), fall back to `main`. Use this as
   `<base>` everywhere below.
3. `git log --oneline <base>..HEAD` — list commits in this branch
4. `git diff <base>...HEAD --stat` — file summary to determine which areas changed (three-dot:
   diffs from the merge-base, so commits that landed on `<base>` after the branch point don't
   show up as spurious changes)
5. Identify the originating GitHub issue:
   - First, check the plan file found in `tasks/` (see Phase 3) — plans typically have `**GitHub Issue**: #123` or a URL on line 3
   - If no plan file, check commit messages and branch name for issue references (e.g., `#123`, `issue-123`)
   - If not found there, search GitHub issues: `gh issue list --search "<branch name or feature keywords>" --state open` and `--state closed`
   - If still no match, ask the user with AskUserQuestion

### Phase 2: Run Lints and Tests

Discover and run the project's lint, format, and test commands:

1. Read the project's `CLAUDE.md` (and `AI_GUIDELINES.md` if present) to find documented lint, format, and test commands
2. From `git diff <base>...HEAD --stat`, determine which areas of the codebase changed
3. Match changed areas to the relevant commands discovered in step 1. For example, if `CLAUDE.md` documents separate commands for `rust/`, `python/`, and `frontend/` directories, only run the checks for directories with changes
4. Launch independent checks in parallel using the Task tool. For each check, the task prompt should include the exact command to run and the working directory
5. If no `CLAUDE.md` exists or no commands are documented for a changed area, ask the user with AskUserQuestion what checks to run

If any check fails, report the failures and stop. Do NOT create the PR. Tell the user what needs to be fixed.

### Phase 3: Plan File Management

The plan file should already be part of the branch's diff (moved/updated and committed). Verify this:

1. Check `git diff <base>...HEAD --stat` for plan file changes in `tasks/`
2. If a plan file was moved to `tasks/completed/`, good — note it for the PR description
3. If a plan file exists in `tasks/` (not `completed/`) and relates to this branch:
   - Read it and check if all implementation steps are completed based on the commits
   - If incomplete, ask the user: "The plan still has incomplete steps. Should I update it and commit before creating the PR?"
   - If done, move it to `tasks/completed/`, commit the move, then proceed
4. If the plan has an associated mockups folder (`tasks/<slug>_mockups/`, referenced from the plan's `## Mockups` section) and it still exists at that path, move it to `tasks/completed/<slug>_mockups/` in the same commit as the plan move
5. If no plan file is found, that's fine — proceed without one

### Phase 4: Update Changelog

Update `CHANGELOG.md` with the changes from this branch.

1. Read `CHANGELOG.md` to understand the current format and the `## Unreleased` section
2. Review the commits (`git log --oneline <base>..HEAD`) and the PR summary you're about to write
3. Add concise bullet points under the `## Unreleased` section:
   - Group under an existing bold category header (e.g., `**Enhancements:**`, `**Bug Fixes:**`) or create a new one if nothing fits
   - Each bullet should be a short description with the issue number in parentheses, e.g., `* Add zoom buttons to chart (#123)`
   - Match the style of existing entries — start with a verb (Add, Fix, Refactor, Update, Remove), include issue/PR number
   - Don't duplicate entries that are already in the changelog
4. Stage and commit the changelog update as two separate calls: `git add CHANGELOG.md`, then
   `git commit -m "Update changelog"`
5. If no `CHANGELOG.md` exists, skip this phase

### Phase 5: Create the Pull Request

1. Make sure the remote has the branch's commits:
   - `git rev-parse --abbrev-ref --symbolic-full-name @{u}` to check whether an upstream is set
   - If there is no upstream, push with `git push -u origin <branch>`
   - If an upstream exists, compare with `git rev-list --left-right --count @{u}...HEAD`:
     if the local branch is strictly ahead, push with `git push`; if it is behind or has
     diverged (the remote has commits the local branch lacks), **stop and report** — never
     force-push, and never pull/rebase automatically; let the user reconcile and re-run

2. Build the PR description:
   - Title: concise summary of the changes (under 70 characters)
   - Body must include:
     - `## Summary` — bullet points describing what changed and why
     - `Closes #<issue>` or `Fixes #<issue>` to link the originating issue (use `Closes` for features, `Fixes` for bugs)
     - `## Test plan` — how to verify the changes work. If the plan file has a
       `## Manual Verification` section, copy its steps in verbatim (commands and expected
       results) alongside the automated coverage, so a reviewer can re-run the manual checks
       straight from the PR body
     - If a plan file was moved to completed, mention it: "Design plan: `tasks/completed/<file>`"

3. Create the PR. Write the body to a scratch file first — do **not** pass it inline (via
   `--body` or a heredoc): PR bodies contain backticks, quotes, and other shell metacharacters
   that the command-safety checker flags, which stalls on a permission prompt. Mint a unique
   path for the body file:
   !`mktemp -u /tmp/pr-body.XXXXXX`
   Write the body to that exact path with the **Write** tool, then:
```
gh pr create --title "<title>" --body-file <body file path>
```

4. Output the PR URL when done.

## Guidelines

- Never force-push or amend commits during this process
- Never add AI attribution: no `Co-Authored-By` lines in commits and no "Generated with Claude
  Code" (or similar) footers in the PR body — commits and the PR must read as authored by the
  repository's normal author
- If lints fail with auto-fixable issues (e.g., formatting), ask the user if they want you to fix and commit before retrying
- The issue link is important — always try to find it before falling back to asking
- Keep the PR title short and descriptive — put details in the body
- Match the existing PR style in the repository
