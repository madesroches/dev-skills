---
name: babysit-pr
description: Watch a pull request's CI until it passes, dispatching a fixer agent to repair any failing checks
argument-hint: "[pr number or url] [— attempt cap N]"
allowed-tools: Bash(gh *), Bash(git *), Bash(mktemp *), Read, Write, Task, Monitor
---

# Babysit PR — Watch CI, Fix What Breaks

Watch the CI checks of an open pull request until they all pass. When a check fails, dispatch a
fresh `{{coding}}` fixer agent to repair it, commit and push the fix, and watch again. Ends when CI is
green, when the attempt cap is hit, or when the problem is not something a fixer can repair.

**Model tiers.** This skill names models by role. `{{coding}}` is the tier for well-specified,
mechanical work — pass `model: "sonnet"`. `{{thinking}}` is the tier for judgment — pass
`model: "opus"`. To run on other models, remap those aliases with Claude Code's
`ANTHROPIC_DEFAULT_SONNET_MODEL` / `ANTHROPIC_DEFAULT_OPUS_MODEL`, or swap the two quoted
values for another alias (`sonnet`, `opus`, `haiku`, `fable`) here.

This skill is **fully autonomous** once started — it does not prompt. It never amends, never adds AI
attribution to commits, and force-pushes only in one case: `--force-with-lease` after rebasing the
PR branch onto the latest base (Phase 1 step 3).

## Roles

- **Orchestrator** — this skill, in the main context. Resolves the PR, polls checks, collects
  failure logs, spawns the fixer, commits and pushes, and writes the summary. It does **not** edit
  code itself.
- **Fixer agent** — a fresh `Task` agent (`subagent_type: "general-purpose"`, `model` = `{{coding}}`)
  spawned per failing round. It receives the failing check names, the relevant log excerpts, and the
  PR branch, diagnoses the root cause in the code, and fixes it in the working tree. It does not
  commit or push.

## Process

### Phase 0: Preflight

1. Resolve the PR from `$ARGUMENTS` (a number or URL). With none, use the current branch's PR:
   `gh pr view --json number,url,headRefName,state`. If there is no PR, say so and stop.
2. If the PR state is not `OPEN`, report it and stop.
3. Make sure the local checkout is the PR's branch (`git branch --show-current` equals
   `headRefName`) and the tree is clean (`git status --short`). If not, report and stop — a fixer
   must never run against the wrong branch or sweep unrelated work into a fix commit.
4. Attempt cap: the number of fix attempts, default **3**, overridable in `$ARGUMENTS`
   (e.g. `attempt cap 5`).
5. Mint a scratch path for commit messages (written to a file and committed with `-F`):
   !`mktemp -u /tmp/babysit-pr-commit-msg.XXXXXX`
   Use this exact path as `<commit msg path>`.

### Phase 1: Watch CI

1. **Watch with `Monitor`.** Arm `Monitor` with `timeout_ms: 1800000` and a `description` naming the PR
   (e.g. `CI checks on PR #<pr>`), running this loop with `<pr>` substituted:

   ```bash
   pr=<pr>; seen=""; any=0; empty=0
   expr='if length == 0 then "EMPTY" else ((.[] | select(.bucket == "fail" or .bucket == "cancel") | "F " + .name), (if all(.[]; .bucket != "pending") then "DONE " + (group_by(.bucket) | map("\(.[0].bucket)=\(length)") | join(" ")) else "PENDING" end)) end'
   while true; do
     s=$(gh pr checks "$pr" --json name,bucket --jq "$expr" 2>/dev/null); [ -n "$s" ] || s=EMPTY
     if [ "$s" = EMPTY ]; then
       empty=$((empty+1))
       if [ "$any" -eq 0 ] && [ "$empty" -ge 3 ]; then echo "NO CHECKS"; exit 0; fi
     else
       any=1; empty=0; d=""
       while IFS= read -r l; do
         case "$l" in
           "F "*) n=${l#F }; grep -qxF -- "$n" <<<"$seen" || { echo "FAILED: $n"; seen="$seen"$'\n'"$n"; } ;;
           "DONE "*) d=${l#DONE } ;;
         esac
       done <<<"$s"
       if [ -n "$d" ]; then echo "ALL DONE: $d"; exit 0; fi
     fi
     sleep 30
   done
   ```

   The loop is silent while checks are pending (`skipping` rows never print). It prints one
   `FAILED: <name>` line per newly failed or cancelled check, the poll it is first seen; one
   `ALL DONE: <bucket counts>` line when no check is pending, then exits; and `NO CHECKS` after three
   consecutive empty polls (~60 s) if no check was ever seen. A transient `gh` error after checks were
   seen is a skipped poll, not "no checks". Any long-lived filter added to the loop must flush per line
   (`grep --line-buffered`, `awk` with `fflush()`).

   Handling events:
   - `FAILED:` — keep the same monitor armed until its `ALL DONE` line, so one fixer pass sees every
     failure. You may fetch the failed check's log (Phase 2 step 2) while waiting.
   - `ALL DONE` / `NO CHECKS` — go to step 2. After `NO CHECKS`, step 2's single re-read is the second
     look, with no further 60-second wait. If that re-read fails with a `gh` error other than "no checks
     reported", report that error rather than **no CI**.
   - **Deadline notice** (the monitor expired with checks still pending) — re-arm it with the same
     command. Each expiry with no `ALL DONE` counts as one consecutive timeout; at **6**, stop and
     report the checks as still pending. Re-arming restarts the loop's `seen` set, so a check already
     reported may print `FAILED:` again — a repeat, not a new failure.

   **Never cancel a healthy watch.** A watch that is still running — a Monitor that has not expired, or
   a Bash command the harness moved to a background job when its timeout hit — is not a failure. Do not
   cancel and restart it; wait for its next event or completion notification. Only a Monitor expiry
   notice or an actual exit of the Bash command ends a wait.

   **Fallback (no `Monitor` tool offered).** Run `gh pr checks <pr> --watch --fail-fast` with the Bash
   `timeout` set to 600000, up to **6** consecutive timeouts (about an hour), then stop reporting the
   checks as still pending. Rerun only when the timeout actually killed the command; a timeout that
   leaves it running in the background is waited on, not rerun.
2. Read the result with `gh pr checks <pr> --json name,state,link,workflow`:
   - **No checks reported at all**: wait ~60 seconds and look once more (checks can lag the push),
     unless this follows `NO CHECKS` (already waited). If still none, report that the PR has no CI and
     stop — nothing to babysit.
   - **All checks passed** (every state `SUCCESS`, or `SKIPPED`/`NEUTRAL`): do step 3, then Phase 3.
   - **Any `FAILURE`/`ERROR`/`CANCELLED`/`TIMED_OUT`**: do step 3, then Phase 2. On the Monitor path
     step 1 already waited for every check; on the fallback path, where `--fail-fast` may return early,
     wait for the rest with `gh pr checks <pr> --watch` so one fixer pass can address every failure at
     once.
3. **Keep the branch current.** Other PRs landing on the base can leave this one `BEHIND` or
   conflicting, and CI then tests stale code or never starts. Before acting on step 2's result, check `gh pr view <pr> --json mergeStateStatus,baseRefName`.
   If it is `BEHIND` or `DIRTY`:
   - `git fetch origin <baseRefName>`, record the remote branch tip (`git rev-parse @{u}`), then
     `git rebase origin/<baseRefName>`. On conflicts, resolve them with the conflict resolver (below).
   - Push with `git push --force-with-lease=<headRefName>:<recorded tip>`. This is the only
     force-push this skill makes: it rewrites only commits this run knows about, and the lease
     refuses if someone else pushed to the branch meanwhile (then stop and report).
   - A rebase is not a fix attempt and does not count toward the cap, but cap it at **3** rebases
     per run. Return to Phase 1 to watch the new run (after the ~30 second pause in Phase 2 step 7).
   A passing result only counts as green if the branch is not `BEHIND`/`DIRTY` when checked.

   **Conflict resolver.** While the rebase is stopped on a commit (`git status` shows unmerged
   paths), spawn a fresh `Task` agent (`general-purpose`, `model` = `{{coding}}`) with the conflicting
   files, the base branch, and the instruction to read both sides — and the commit being replayed
   (`git show REBASE_HEAD`) and what landed on the base — and edit the files so the result keeps the
   intent of **both** changes, with no conflict markers left. It must not run `git add`, `git commit`,
   or any `git rebase` command; if the right resolution is genuinely ambiguous (the two sides
   contradict each other), it says so instead of guessing. Then the orchestrator checks for leftover
   markers (`git diff --check`), stages the resolved files by explicit path, and runs
   `GIT_EDITOR=true git rebase --continue`; a later commit that conflicts gets a fresh resolver. If a
   resolver reports ambiguity, leaves markers, or the rebase has stopped more than **5** times,
   `git rebase --abort` and **stop and report** the conflicting files (outcome **blocked**). Record
   each resolved file and a one-line description of how it was resolved for the summary — resolutions
   are never silent. Before the push, if the project's `CLAUDE.md` documents a fast build or check
   command, run it once; if it fails, do not push: report the check output and the resolved-files
   summary, and stop with outcome **blocked** (the branch is left rebased locally, unpushed).

### Phase 2: Fix

1. If the attempts used equals the cap, stop (see Phase 3 outcomes: attempt cap).
2. Gather the failure evidence for each failed check: the run id is in its `link`
   (`.../actions/runs/<id>/...`); fetch `gh run view <id> --log-failed` and keep the relevant tail
   (the failing step's output, not the whole log). If the link is not a GitHub Actions run (an
   external status), the logs may be unreachable: include what `gh pr checks` gives and tell the
   fixer so.
3. If every failure looks **non-code** — runner or infrastructure errors, a cancelled run, a
   timeout with no failing step, a missing secret or permission — do not spend an attempt on a
   fixer: for a transient-looking one re-run it once (`gh run rerun <id> --failed`) and return to
   Phase 1; otherwise stop and report it as unfixable from code.
4. Spawn the fixer (`Task`, `general-purpose`, `model` = `{{coding}}`) with: the PR number and branch,
   each failing check's name and log excerpt, the instruction to find the **root cause** and make
   the smallest correct change (no suppressing or deleting the failing test or lint rule, no
   unrelated edits), to run the failing check locally if the project's `CLAUDE.md` documents a
   command for it, and to report what it changed and why — or that it could not fix it. It must
   not commit or push.
5. If the fixer reports it could not fix the failure, stop and report that, with its reasoning.
6. Otherwise commit and push, as separate calls:
   - Check `git status --short` has changes; if the fixer changed nothing, treat it as "could not
     fix" (step 5).
   - Write a message to `<commit msg path>` with the Write tool — subject `Fix CI: <short
     description>` (≤ 72 chars), body naming the failing checks. **No AI attribution** — no
     `Co-Authored-By`, no agent credit.
   - `git add <file> [<file> ...]` by explicit path from the status output — never `git add -A`.
   - `git commit -F <commit msg path>`.
   - `git push`. If it is rejected (the remote moved), fetch and treat it as Phase 1 step 3 if the
     cause is the base branch advancing; if someone else pushed to the PR branch, stop and report
     — never force-push over another author's commits. If the push is blocked by a permission gate, stop and report that
     the fix is committed locally but unpushed.
7. Count the attempt and return to Phase 1. Waiting for the new run starts with a ~30 second pause,
   so `gh pr checks` reflects the new commit rather than the stale failed run.

### Phase 3: Summary

Report concisely:
- The PR (number + URL) and the final outcome, one of: **green** (all checks passed), **attempt cap**
  (checks still failing after N attempts, with the failing check names), **unfixable** (non-code
  failure or the fixer could not fix it, with why), **no CI**, **still pending** (the watch hit its
  timeout cap), or **blocked** (push rejected or gated).
- For each fix attempt: the commit subject and which checks it addressed.
- Each rebase conflict resolved: the file and how it was resolved, so the user can review it.
- Any check still red, with a link, so the user can pick up from there.

## Notes

- **Fixer is `{{coding}}`, fresh each attempt.** A new agent per round sees only the current failure,
  not previous rounds' reasoning; the orchestrator holds the attempt count.
- **Rebase over merge.** Matching `pr`'s rebase-onto-base convention keeps history linear; the
  lease-guarded force-push is safe because the branch is this run's own PR branch.
- **Only the PR's own CI.** This skill does not review code, address review comments, or merge.
- **Cap everything.** Both the fix attempts and the waiting (the consecutive-expiry cap) are bounded, so the skill cannot spin
  forever on a flaky or permanently red pipeline.
- **No restated logic.** It reads `CLAUDE.md` only via the fixer's local-run hint; it does not
  duplicate `pr`'s lint/test discovery.
