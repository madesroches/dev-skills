# babysit-pr: Watch CI with Monitor Plan

**GitHub Issue**: https://github.com/madesroches/dev-skills/issues/23

## Overview
`babysit-pr` Phase 1 waits on CI with `gh pr checks <pr> --watch --fail-fast`, which reprints the full checks table every 10 seconds (about 1,000 lines per 10-minute watch) and assumes a Bash timeout kills the command. Switch the watch to the `Monitor` tool running a quiet poll loop that prints one line only on a state change, keep the Bash `--watch` path as a fallback for harnesses without Monitor, and state that a still-running background watch is not a failure.

## Current State
- `skills/babysit-pr/SKILL.md` frontmatter: `allowed-tools: Bash(gh *), Bash(git *), Bash(mktemp *), Read, Write, Task`.
- Phase 1 step 1 (`skills/babysit-pr/SKILL.md:52`): `gh pr checks <pr> --watch --fail-fast` under a Bash `timeout` of 600000, rerun on timeout up to **6** consecutive timeouts (about an hour), then stop with outcome **still pending**.
- Phase 1 step 2 reads `gh pr checks <pr> --json name,state,link,workflow` and branches on: no checks (wait ~60 s, look once more, else **no CI**), all passed, any failed. On failure it waits for the remaining checks with a second `gh pr checks <pr> --watch` (line 61) so one fixer pass sees every failure.
- Phase 2 step 7 returns to Phase 1 after a ~30 second pause.
- `scripts/validate.py:38` `HEURISTIC_TOOLS = ("Task", "Skill", "AskUserQuestion")`: a capitalized tool name in a skill body must appear in `allowed-tools`.
- `gh pr checks --json` exposes a `bucket` field (`pass`, `fail`, `pending`, `skipping`, `cancel`). `gh pr checks` exits non-zero while checks are pending or failing but still prints the JSON.
- Monitor contract: each stdout line is one event; the command's exit ends the watch; `timeout_ms` defaults to 300000 and is capped at 1800000; on expiry the monitor is killed and one notice is sent, and the caller re-arms.

## Design

### Primary path: Monitor
Phase 1 step 1 becomes: arm `Monitor` with `timeout_ms: 1800000` (the maximum) and a `description` naming the PR (e.g. `CI checks on PR #<pr>`), running this loop with `<pr>` substituted:

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
        "F "*) n=${l#F }; grep -qxF "$n" <<<"$seen" || { echo "FAILED: $n"; seen="$seen"$'\n'"$n"; } ;;
        "DONE "*) d=${l#DONE } ;;
      esac
    done <<<"$s"
    if [ -n "$d" ]; then echo "ALL DONE: $d"; exit 0; fi
  fi
  sleep 30
done
```

Behavior:
- Silent while checks are pending. `skipping` rows never print (they are neither failed nor pending).
- One `FAILED: <name>` line per newly failed or cancelled check, the poll it is first seen — so an early failure is reported without waiting for slower checks.
- One `ALL DONE: <bucket counts>` line when no check is pending, then the loop exits, ending the watch.
- `NO CHECKS` after three consecutive empty polls (~60 s) if no check was ever seen; a transient `gh` error after checks were seen is treated as a skipped poll, not as "no checks".
- Flushing: every event is written by `echo` from the loop's own shell, and the only filters (`gh --jq`, `grep -q`) are per-poll processes that exit, so no long-lived pipe stage holds output in a buffer. The skill states the rule so a later edit does not add one: any long-lived filter added to the loop must flush per line (`grep --line-buffered`, `awk` with `fflush()`).

Orchestrator handling of events:
- `FAILED:` — the existing "wait for the rest so one fixer pass sees everything" rule applies: keep the same monitor armed until its `ALL DONE` line (it replaces the second `--watch` on line 61). The orchestrator may fetch the failed check's log (Phase 2 step 2) while waiting.
- `ALL DONE` / `NO CHECKS` — proceed to step 2, which re-reads `gh pr checks --json name,state,link,workflow` and applies the existing branches unchanged (the `NO CHECKS` line stands in for the first of its two looks).
- **Deadline notice** — the monitor expired with checks still pending: re-arm it with the same command. Each expiry with no `ALL DONE` counts as one consecutive timeout against the existing cap of **6**; at the cap, stop with outcome **still pending**. Re-arming restarts the loop's `seen` set, so a check already reported may print `FAILED:` again; that is a repeat, not a new failure.

### Never cancel a healthy watch
New explicit rule in Phase 1, covering both paths: a watch that is still running — a Monitor that has not expired, or a Bash command the harness moved to a background job when its timeout hit — is not a failure. Do not cancel and restart it; wait for its next event or its completion notification. Only an expiry notice (Monitor) or an actual exit of the command (Bash) ends a wait.

### Fallback: Bash `--watch`
When the `Monitor` tool is unavailable (not offered by the harness), use the current path unchanged: `gh pr checks <pr> --watch --fail-fast` with the Bash `timeout` at 600000, the second `--watch` after a failure, and the cap of 6 consecutive timeouts — with the rule above applied: a timeout that leaves the command running in the background is waited on, not rerun; it is rerun only when the timeout actually killed it.

### Frontmatter and validator
- `allowed-tools` gains `Monitor`. The loop uses `gh`'s built-in `--jq`, so no external `jq` binary is required, and no `Bash(...)` entry is needed because the loop runs inside Monitor, not as a Bash tool call.
- `scripts/validate.py` `HEURISTIC_TOOLS` gains `"Monitor"`, so a skill body that names Monitor without declaring it fails CI; update the module docstring's tool list to match.

## Implementation Steps
1. `skills/babysit-pr/SKILL.md`:
   - Add `Monitor` to `allowed-tools`.
   - Rewrite Phase 1 step 1 per **Primary path** (loop, `timeout_ms`, event handling, re-arm and cap), followed by the **Never cancel a healthy watch** rule and the **Fallback** paragraph.
   - In Phase 1 step 2's failure branch, replace "wait for them too (`gh pr checks <pr> --watch`)" with "keep the step 1 watch running until it reports all done (fallback: `gh pr checks <pr> --watch`)".
   - In Phase 3's **still pending** outcome, say the watch hit its timeout cap.
   - Notes: in **Cap everything**, mention that the watch is bounded by the consecutive-expiry cap.
2. `scripts/validate.py`: add `"Monitor"` to `HEURISTIC_TOOLS` and to the docstring list at line 15.
3. `.claude-plugin/plugin.json`: bump version to `1.35.0`.
4. `CHANGELOG.md`: add a `1.35.0` entry describing the Monitor watch, the fallback, and the never-cancel rule.
5. Run `python3 scripts/validate.py` and `python3 scripts/test_validate.py`.

## Files to Modify
- `skills/babysit-pr/SKILL.md`
- `scripts/validate.py`
- `.claude-plugin/plugin.json`
- `CHANGELOG.md`

## Trade-offs
- **Monitor deadline: maximum (30 min) with the cap of 6 kept**, as the issue proposes. This raises the longest wait from about one hour to about three hours on the Monitor path; each expiry costs one notice line, so a longer bound is cheap. The fallback keeps its ~1 hour bound.
- **Poll loop vs. `gh pr checks --watch` piped through a filter.** A filter over `--watch` still runs the 10-second redraw and needs buffering care at every stage; the poll loop prints nothing until state changes and needs no long-lived pipe stage.
- **Fallback keeps `--watch` as-is** (per the issue) rather than running the quiet loop under Bash; it only applies where Monitor is absent.

## Decisions

## Documentation
- `CHANGELOG.md` entry (step 4). README and `CLAUDE.md` describe `babysit-pr` at a level this change does not affect.

## Testing Strategy
- `scripts/validate.py` (run in CI) catches a body that names Monitor without declaring it, and frontmatter/version/CHANGELOG drift.
- No unit test for the loop: it is shell embedded in skill prose with no harness in this repo, and its behavior depends on live `gh` output.

## Manual Verification
1. On any open PR with running CI, run the loop from **Primary path** under `Monitor` (e.g. `/babysit-pr <pr>`). Expected: no output while checks are pending, one `FAILED: <name>` per failing check, and a final `ALL DONE: pass=N ...` line when CI finishes. Not automated because it needs a live PR and CI run; a broken loop is visible immediately as missing or flooding events.
