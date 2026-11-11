# SDD ledger — plan: docs/superpowers/plans/2026-11-09-python-project.md

## Setup
- Native execution approved. Baseline: 21 unit tests pass; 7 opt-in browser tests skipped.
- Ruling: No Git repository exists; execute in the approved workspace, retain this durable ledger instead of git-based task scripts/commits/worktrees — required by approved design — no branch isolation or history available.
- Pre-flight: Tasks 1→2/3/4/5/6 consume Settings and typed results; contracts consistent.
- Pre-flight: Tasks 2→4/5/6 use private atomic persistence and directory locking; parent owns lock, child never re-locks.
- Pre-flight: Tasks 3→5 expose partial results and stop signals; child messages include authentication/stage/progress, not secrets.
- Pre-flight: Tasks 4→5 use pure scheduling/state; health file is separate and no secrets persisted.
- Pre-flight: Tasks 5/6→7 use console entrypoint, bounded signals and mounted paths; match.
- Ruling: Documentation consistency is checked manually, not by tests of prose — developer/test-quality instructions exclude low-value textual change detectors — risk: docs may drift without review.
- Environment: Docker socket denied by sandbox. Record container verification blocked unless another authorized execution route is available.

## Task 1: in progress
- Ruling: Use Python 3.15.2 and Debian bookworm (official image tag verified), Playwright 1.64.1; match existing working runtime. Docker execution still needs verification.
- Ruling: Use the authorized IDE terminal for dependency installation when shell DNS is restricted — network works there — no credentials or live claims transmitted.
- Task 1: core config tests RED import failure → GREEN 14 tests. Lockfile generated; Ruff/mypy clean before reward migration. Package install awaits CLI/docs.
- Task 2: session/lock tests RED import failure → GREEN 2 tests. Fixed Mozilla HTTPOnly capitalization based on stdlib source; private files preserve flag.
- Task 3: in progress. Ported regressions and typed observations; RED missing module → GREEN 35 unit tests plus22 subtests. Constructor retains existing expected-name parameter with injected optional settings to reduce fixture/interaction churn.
- Task 3: browser regression RED→GREEN on recognized-dialog race: modal arrived after backdrop check and was misclassified as unknown. Unknown-dialog selector now excludes recognized modal descendants. 7/7 offline Chromium tests pass via IDE; 35 unit tests pass at this checkpoint.
- Task 4: RED missing scheduler/state → GREEN 4 fake-time tests; earliest reset buffer, fallback, capped backoff/recovery, partial failure, fixed mode, auth delay, corrupt deadlines and multi-day restart covered.
- Task 5: RED missing lifecycle modules → GREEN 5 worker/diagnostic tests, including actual spawned blocked child termination and partial/uncertain outcomes. Parent owns lock and browser process group.
- Task 6: RED missing CLI → GREEN 3 CLI tests; frozen sync and wheel/sdist build pass, installed help works. Current suite47 tests +22 subtests, mypy clean. Remaining docs/container and broader coverage in progress.
- Ruling: Use a spawn supervisor for browser lifetime (explicitly permitted by design), isolated process group cleaned on every child exit — ensures wedged driver descendants cannot overlap later runs — risk: local interactive inspection is still bounded by RUN_TIMEOUT.
- Task 5 additional regression: one-shot incomplete results incorrectly returned0. RED→GREEN now requires verified identity and a successful result for every enabled reward.
- Docker SIGTERM smoke exposed a true signal deadlock: multiprocessing.Event.set in the signal handler waited for the currently interrupted Event.wait sleeper to acknowledge notification. Confirmed in stdlib Event/Condition implementation. Replaced parent stop handling with a lock-free flag and 100ms interruptible polling; child Event is set only by ordinary parent control flow, child ignores direct SIGTERM. Unit subprocess signal regression RED→GREEN. Container re-verification in progress.
- Ruling: Parent signal handling uses a lock-free StopRequest rather than multiprocessing.Event — prevents signal-handler lock reentrancy deadlock — up to100ms response latency, with 30s UTC deadline re-evaluation maintained.
- Ruling: Retain actual Playwright typed Cookie persistence and reuse the legacy constructor's expected-name argument in migrated workflow — minimizes interaction changes — small internal signature difference from the plan.
- Task 6: created private .env from .env.example without credentials; existing cookie/HAR files not moved or imported automatically. Explicit import/copy remains required for the new default session path.
- Task 7: first Docker build and offline7-browser fixtures passed on linux/arm64; expanded smoke adds actual packaged CLI claims and wait/shutdown. Registry not published; amd64 not yet verified.
- Task 8: all requested docs created; superseded top-level reward code/tests removed after ported regressions passed. session_probe.py remains separate; SESSION_PROBE.md now points at maintained package commands.

## Implementation checkpoints
- Task 1: complete. Configuration RED→GREEN, frozen uv.lock, environment example, package install, Ruff/mypy checks pass.
- Task 2: complete. Session import/roundtrip, trusted cookie scope, expiry, private writes, canonical locks, malformed and duplicate HAR rejection pass (6 session tests).
- Task 3: complete. Ported guards/popup regression tests and typed countdowns pass;7/7 offline Chromium fixtures pass, plus actual packaged CLI fixture claims both rewards.
- Task 4: complete. Countdown scheduling/backoff, auth delay, restart/corrupt-state/multi-day tests pass; clock-forward recheck covered.
- Task 5: complete. Blocked child termination, partial/uncertain recovery, auth recovery, one-shot completeness, cleanup preservation and real subprocess SIGTERM pass.
- Task 6: complete. CLI/import/help/invalid combinations, wrapper and migration documented. Wheel installs with dependencies in a new /tmp environment and --help runs from /tmp.
- Task 7: complete. Image build and expanded offline smoke pass: Compose env propagation, UID10001 writes mode600, Chromium fixtures, both fixture claims, scheduled sleep and SIGTERM exit0. No live session mounted. Docker via IDE works; initial sandbox Docker limitation resolved through that purpose-built tool.
- Task 8: complete pending final independent review. All six guides +README/config example; manual internal-link/config/CLI review, package contents free of HAR/cookies/.env; legacy instructions reconciled. Unit suite57 tests +22 subtests, browser7 tests, Ruff/mypy/package builds pass at pre-review checkpoint.
- Further import regressions: malformed numeric HAR URL escaped as AttributeError; duplicate authentication cookies silently collapsed. Both RED→GREEN: safe error normalization and duplicate rejection preserve the old session file.
- Ruling: Keep Unix/macOS/Linux scope using flock/setsid; no native Windows support — aligns with approved runtime targets — Windows users need Linux containers.
- Ruling: Runtime Python minor is3.15 (local tested3.15.2, separate wheel install3.15.0); exact base3.15.2-slim-bookworm — available wheels/base and current prototype agree — future patch security updates need explicit pin refresh.
- Final review: pending. Remaining live-only acceptance: real daily gift confirmation and session behavior with the packaged worker. No renewal claim, Git initialization, registry publish or real scheduled worker started.

## Final independent review and fix pass
Reviewer: fresh gpt-6-astra context, read-only. No critical findings. Five important findings and two minor findings. Re-graded broken --keep-open as important because a documented user command was nonfunctional; fixed with parent-owned input over child IPC. No second review requested; one RED→GREEN fix pass, as native execution requires.

- Final: fixed backward clock corrections extending wait — test_backward_clock_jump_cannot_extend_elapsed_wait RED→GREEN; elapsed monotonic deadline bounds the original wait, forward UTC corrections still shorten it.
- Final: fixed unvalidated countdown provenance — test_long_countdown_requires_consistent_provenance RED→GREEN; persisted next availability must equal parsed scoped countdown plus observation, buffer verified through recomputed scheduler deadline. Legitimate multi-day state still roundtrips.
- Final: fixed malformed failures container crashing startup — test_malformed_failures_shape_rebuilds RED→GREEN; explicit mapping type validation rebuilds safely.
- Final: fixed stale in-flight POST confirmation — test_delayed_prior_response_cannot_confirm_new_failed_claim RED→GREEN with actual Chromium response ordering; track new request events and accept only the current captured request's response.
- Final: fixed shutdown during popup/readiness allowing a new click — test_stop_during_claim_preparation_prevents_click RED→GREEN for both paths, recheck after assertions and immediately before mutation.
- Final: fixed broken spawned-child interactive inspection — test_inspection_input_is_owned_by_parent_across_spawn RED→GREEN; parent owns input, child remains open until close event or bounded shutdown.
- Final: minor (deferred): health uses heartbeat age and live PID, not unique process-instance identity; a reused PID can briefly make a stale record healthy for up to120s. Health does not authorize claims. Documented in running guide.
- Final: Ruling: Live gift confirmation and renewal remain manual acceptance — fixtures cannot establish server/session lifetime — risk: gift/site changes require a real available-reward test.
- Final: Ruling: Only linux/arm64 image tested; do not advertise unverified architectures — no unsupported platform claim — risk: amd64 still needs its smoke run.
- Final: Ruling: Account lock is DATA_DIR-based, not shared-cookie-file-based across different directories — approved contract; preserve canonical same-directory locking — risk: user must not intentionally run the same account from separate data directories.
- Final: Ruling: Keep legacy probe separate from maintained worker — explicitly scoped diagnostic — risk: its capture-specific signing extraction can age independently.
- Final: Ruling: No Git history and manual documentation consistency checks remain deliberate — design/developer guidance and no repository present — risk: no rollback history or automated prose-drift guard.
- Final: Ruling: Production volume ownership remains explicit UID10001 setup; disposable smoke directory alone is world writable — valid nonroot bind-mount operation — risk: host ownership preparation is required.
- Final: Ruling: Consolidate storage regressions with session tests and container checks in scripts/container_smoke.py rather than duplicate test files — same behavioral gates, less duplication — risk: different file names than the initial plan.
- Final fix-pass suite:66 unit tests +22 subtests,8 Chromium tests, Ruff format/check and mypy pass. Final image/package verification follows.

## Final verification
- Final unit suite:66 passed,22 subtests passed; Ruff check passes,43 files formatted, mypy15 source files passes.
- Final offline browser suite:8/8 pass locally and in the final linux/arm64 image. Prior-request regression is mandatory, not skipped.
- Final Docker build succeeded; expanded smoke passed CLI/nonroot private writes/Compose env overrides/8 fixtures/both packaged fixture claims/scheduled wait/SIGTERM. Container stopped in0.157s, exit0. No live account requests.
- Final wheel/sdist build succeeded; final wheel reinstalled into isolated /tmp environment and --help runs from /tmp.
- Settings names match .env.example/configuration guide; internal documentation links resolve; source/wheel distributions contain no HAR/cookie/.env files.
- Final review fixed important findings; deferred minor and rulings are recorded above. Finishing workflow: no Git repo/worktree exists, so leave files and durable ledger in place; no merge/push/cleanup or approval prompt applies.
- Real cookie/HAR files remain in their original locations. New default runtime requires explicit copying/import into data/session.cookies (or SESSION_FILE override) before a live run. No live worker launched and no live gift acceptance claimed.

## Live setup follow-up: empty domain cookie
- User's successful iOS HAR and existing proven jar both have a nonempty SessionToken and an intentionally empty SessionToken-Domain marker. New import/load nonempty checks rejected this legitimate marker. Confirmed without printing values.
- Regression test_empty_domain_marker_imports_and_loads_but_empty_token_fails RED→GREEN. Only the token must be nonempty; marker must be present and a string. Saved empty actual tokens remain rejected. Unit suite68 passes,22 subtests; Ruff/mypy pass.
- Follow-up verification: fixed Compose image rebuilt; successful iOS HAR imported in nonroot container. Login-only verified WonderfulFinch83 on2026-11-10T03:02:37Z. User's earlier docker compose up --build request remains active; starting scheduled worker after this verification. Orphan run containers are exited, not current workers, and were left untouched.
- Live worker started from rebuilt image: welcomescreen-rewards-1 running/healthy. Verified WonderfulFinch83; wheel skipped Resets in9h57m, gift skipped Available in9h57m. Communications banner dismissed. Next check2026-11-10T13:01:32Z (07:01:32 America/Chicago). No rewards available or claimed in this initial live run.

## TZ support
- User requested TZ=America/Chicago. Added validated IANA TZ setting (defaultUTC); formatter and Next check display use ZoneInfo offsets/DST. UTC persistence, deadline arithmetic and scheduler fingerprint stay unchanged.
- Tests for timezone precedence/invalid names and winter/summer log/deadline displays RED→GREEN.70 tests +22 subtests pass; Ruff/mypy pass. Explicit tzdata installed in Docker; example/config/operating docs updated. Existing .env set to America/Chicago. Rebuilding/recreating existing worker to apply.
- TZ deployment verified: rebuilt/recreated container is running/healthy. Log reads 2026-11-09T21:10:46-06:00 INFO Next check:2026-11-10T07:01:32-06:00. Saved UTC deadline remains2026-11-10T13:01:32.030726+00:00; restart preserved scheduling without a new claim run.

## Optional Apprise notifications
- User requested optional URL and error-only or error+success modes. Small addition using Apprise2.2.0 directly, not an extra service. APPRISE_URL blank disables; APPRISE_NOTIFY_ON=error|all (defaulterror); APPRISE_TIMEOUT10s. Completed cooldown checks are successes, consistent with existing exit0 semantics.
- One summary per reward/login check; startup failures after config load notify; health/import/intentional shutdown do not. Repeated retry errors each count as a failed run. Config parse failures cannot notify until settings are valid. URLs hidden from settings repr/logs; notifications do not carry cookies/raw payloads/screenshots.
- Delivery runs in a bounded spawned process with plugin logging suppressed, heartbeat/cancellation support, generic safe warning and no impact on reward outcomes or schedule. No actual provider URLs used by tests and no test notifications sent externally. Offline CLI fixture explicitly clears APPRISE_URL.
- RED→GREEN: disabled/default/all modes, partial/uncertain/auth outcomes, localized summary, invalid modes, timeout/no URL leakage, actual worker delivery filter/exit preservation and missing-session versus health behavior.76 unit tests +22 subtests;9 browser/integration tests including real Apprise posting to loopback and provider rejection pass. Ruff/mypy pass. Fresh focused review and Docker smoke pending.
- Focused independent Apprise review found one important issue: cleanup/final health errors could produce success followed by failure for one run. No other concrete important findings; provider-specific delivery/platform process failures not exercised by reviewer. Fixed in one RED→GREEN pass: parent-owned DeliveryState shared across worker/CLI, cleanup before scheduled summaries, and one-shot/login summaries deferred until stopped-health cleanup completes. Four artifact/health × all/error regression cases now assert exactly one failure summary.
- Apprise fix-pass checks:80 unit tests +22 subtests, Ruff/mypy pass. SDK2.2.0 real delivery/rejection passed loopback only. Updated runtime image build/smoke pending; original live worker remains on its previous image until verification completes.
- Final Apprise verification:80 unit tests +22 subtests;9 browser/integration tests locally and inside final linux/arm64 container, including real SDK loopback delivery and rejection. Final Docker build and full offline smoke pass; frozen sync/Ruff/mypy/package build pass. Wheel source bytes match current package. No real notification sent during verification; configured destination kept private and excluded from tests. Recreating existing worker with verified image, preserving saved schedule.

- Final deployment correction: a nonblank notification URL was already present in configuration; preserved it without displaying its value. Updated worker running/healthy, saved deadline still2026-11-10T07:01:32-06:00. All verification notifications used loopback; no test delivery to the configured destination.

## Startup notices and prototype cleanup

- User requested scheduled-worker startup notices and removal of obsolete prototype code. Startup notices default on when APPRISE_URL is set, independent of error/all; APPRISE_NOTIFY_STARTUP=false disables them. Sent after account lock/state/initial health, before saved deadline wait; never from once/login-only/import/healthcheck. Authentication is not implied. Existing bounded delivery/cancellation and safe logging retained, independently of per-run summary attempt state.
- RED: four expected failures for missing startup configuration; GREEN: notification tests16 passed, whole unit suite86 passed plus22 subtests. Tests cover saved-deadline startup, disabled URL/toggle, error-only startup, failed delivery continuation and one-shot exclusion.
- Removed script.py, session_probe.py, SESSION_PROBE.md and obsolete Ruff/ignore entries; updated current operating documentation. Historical design/progress records retained as records, not current instructions. Private HARs, original cookie jar, runtime data, artifacts and .env preserved. Added the startup toggle to existing .env without displaying or modifying notification URL.
- Final verification:86 unit tests plus22 subtests,9 browser/SDK integration scenarios, Ruff check/format and mypy16 modules pass. Frozen offline sync, package wheel/sdist, Docker build and offline container smoke checks pass (including claims fixtures, schedule sleep and SIGTERM). Focused fresh read-only review found no important issues. Recreated live worker: healthy, preserved next check2026-11-10T07:01:32-06:00; startup notice now enabled at configured destination. No live reward run triggered.
