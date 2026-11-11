# Python Project and Scheduled Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Package the working single-account free-reward automation as a documented, configurable, internally scheduled Python application that runs locally and in Docker.

**Architecture:** Preserve the guarded Playwright workflow behind typed inputs/results. A parent process owns configuration, the account lock, persisted scheduling, signals, and health; each browser run executes in a spawned child with bounded lifetime. Scheduling decisions are pure functions of UTC observations and failure history; Chromium closes between runs.

**Tech Stack:** Python, uv, setuptools, Playwright, python-dotenv, dataclasses, argparse, stdlib logging/multiprocessing, pytest, Ruff, mypy, Docker Compose, GitHub Actions. Verify and pin compatible Python/Playwright/build-image versions during Task 1 before committing a lockfile; the existing environment is Python 3.15.2 with Playwright 1.64.1, not a guarantee of container compatibility.

**Spec:** [Approved design](../specs/2026-11-09-python-project-design.md). Read it before executing this plan.

## Global Constraints

- One account; exact configured API DisplayName and visible username required before any claim.
- Only the explicitly free wheel and free shop gift; no paid/loyalty-point actions, generic mutation retries, or fabricated login tokens.
- Defaults: CHECK_INTERVAL=auto, FALLBACK_INTERVAL=15m, RESET_BUFFER=90s, ERROR_RETRY_INTERVAL=5m, ERROR_RETRY_MAX_INTERVAL=1h, AUTH_RETRY_INTERVAL=1h.
- Defaults: HEADLESS=true, both rewards enabled, ACTION_TIMEOUT=15s, NAVIGATION_TIMEOUT=45s, READINESS_TIMEOUT=45s, RUN_TIMEOUT=5m, SHUTDOWN_TIMEOUT=20s.
- Default paths: DATA_DIR=./data, SESSION_FILE=session.cookies relative to DATA_DIR, ARTIFACT_DIR=./artifacts; ARTIFACTS_ENABLED=true, ARTIFACT_RETENTION_DAYS=7, LOG_LEVEL=INFO, LOG_DIR unset.
- EXPECTED_USERNAME is required; documentation example WonderfulFinch83. Environment overrides dotenv; explicit supported CLI flags override environment.
- Browser and API confirmations must agree before recording a confirmed claim. Preserve working popup/race fixes and partial results.
- Runtime does not read HARs. Session import is explicit and offline; expired-session renewal is unproven.
- Local/container Python minors agree. Install browsers and OS dependencies at image build time; nonroot, headless runtime, no application ports.
- CI/tests use synthetic credentials and offline routes only; do not run the live workflow to verify this refactor.
- No Git repository currently exists. Do not initialize Git, commit, create remotes, or publish images. At each task checkpoint record changed files and verification in the progress document instead of committing.

## Review Focus

1. Clock jumps or malformed persisted future deadlines must not prevent future checks (Task 4).
2. A response from an earlier claim must not confirm the current claim (Task 3).
3. A killed child or interrupted submitted claim must retain partial results and never cause an immediate mutation retry (Task 5).
4. Two processes and relative/symlinked paths must not bypass the shared account lock (Task 2).
5. Docker interpolation and host ownership must not silently override `.env` choices or make runtime volumes unwritable (Task 7).

## File Map and Contracts

- `pyproject.toml`, `uv.lock`, `.python-version`: package metadata, frozen dependencies, tool configuration, verified Python minor.
- `src/monopolygo_rewards/{__init__,__main__,cli}.py`: installable entry points and commands.
- `config.py`, `models.py`, `errors.py`: validated settings, immutable typed results, focused error types.
- `session.py`, `storage.py`: cookie import/persistence, private atomic files and canonical directory locking.
- `rewards.py`, `browser.py`: guarded interactions and browser-run ownership.
- `scheduler.py`, `state.py`: pure scheduling plus validated JSON state.
- `worker.py`, `supervisor.py`: long-running loop, spawned browser runs, signals and bounded cleanup.
- `diagnostics.py`: safe logging, private screenshots and bounded retention.
- `tests/unit/`, `tests/browser/`, `tests/container/`, `tests/fixtures/`: isolated tests and synthetic pages/data; `scripts/container_smoke.py` runs container lifecycle checks.
- `Dockerfile`, `.dockerignore`, `compose.yml`, `.github/workflows/ci.yml`: image and offline CI.
- `README.md`, `.env.example`, `docs/{setup,session,running,configuration,development,troubleshooting}.md`: user and contributor documentation.
- `script.py`: thin compatibility wrapper; `session_probe.py` and `SESSION_PROBE.md`: retained diagnostic tool, separate from runtime imports.
- This directory's `2026-11-09-python-project-progress.md`: execution checkpoint evidence and limitations.

All timestamps are timezone-aware UTC. `Reward` is a string enum (`wheel`, `gift`); `RewardStatus` is a string enum (`claimed`, `skipped`, `failed`, `uncertain`). `RewardResult` holds `reward`, `status`, `reason`, `observed_at`, `countdown_text: str | None`, `next_available_at: datetime | None`. `RunResult` holds `results: tuple[RewardResult, ...]`, `auth_status` (`verified`, `blocked`, `unknown`), `finished_at`, and safe optional error. A block can mean wrong identity or rejected credentials; do not collapse network timeouts into authentication rejection.

### Task 1: Establish the package and validated configuration

**Files:** Create pyproject.toml, uv.lock, .python-version, src/monopolygo_rewards/{__init__,config,models,errors}.py, tests/unit/test_config.py, .env.example; extend .gitignore; start docs/development.md and progress document.

**Interfaces:** `parse_duration(value: str, *, allow_zero: bool = False) -> timedelta`; immutable `Settings` with fields from the spec; `load_settings(env_file: Path | None = None, overrides: Mapping[str, str] | None = None) -> Settings`; model contracts above. Configuration errors identify setting names, not supplied values.

- [x] Write parameterized failing tests asserting `parse_duration('1h 30m') == timedelta(minutes=90)`, `parse_duration('90s') == timedelta(seconds=90)`, zero rejected except for buffer, invalid/duplicate/unknown units rejected. Assert `EXPECTED_USERNAME` missing fails; both rewards disabled fails only for run commands; process env beats dotenv and overrides beat both; invalid boolean and max retry below initial retry fail without leaking values. Disable dotenv interpolation so literal settings cannot expand secrets unexpectedly.
- [x] Run `uv run --with pytest pytest tests/unit/test_config.py -q`; expect collection/import or unimplemented-function failure before implementation. Dependency-resolution errors are blockers to fix, not the intended red result.
- [x] Verify available supported Python/Playwright wheels and Debian/Ubuntu image tags using official sources. Select matching local/container Python minor, exact runtime dependency pins, setuptools packaging and mypy tooling; generate uv.lock with uv. Implement configuration/models/errors and expose the complete settings table in .env.example. Resolve all relative paths from startup cwd, except SESSION_FILE relative to DATA_DIR.
- [x] Run `uv run pytest tests/unit/test_config.py -q`, `uv run ruff check src tests/unit/test_config.py`, and `uv run mypy src/monopolygo_rewards`; expect passes. Record version selection and any installation restrictions; document `uv sync --frozen` and the verified Python prerequisite.
- [x] Checkpoint files and results in the progress document; no Git action.

### Task 2: Isolate offline session import, private storage, and account locking

**Files:** Create session.py, storage.py, tests/unit/test_session.py, tests/unit/test_storage.py, docs/session.md; adapt existing cookie-loading tests without deleting the originals until their migrated versions run.

**Interfaces:** `import_har(source: Path, destination: Path) -> None`; `load_cookies(path: Path) -> list[Cookie]` using Playwright's typed Cookie; `save_cookies(path: Path, cookies: Sequence[Cookie]) -> None`; `atomic_write_json(path: Path, payload: Mapping[str, object]) -> None`; `account_lock(data_dir: Path) -> ContextManager[None]`. Use canonical path and Unix flock for the supported macOS/Linux platforms, keeping the descriptor open for the owner's lifetime.

- [x] Write failing tests: successful synthetic HAR import needs only authentication cookie data, never the captured JS/signing key; imported Mozilla file loads with existing domain/expiry rules; expired/partial/foreign-domain sessions fail; failed save leaves the original file intact; output mode is 0600 where supported. Assert held lock blocks a second process even via a symlink alias; lock releases after process death. No tests consume real workspace HAR/cookies.
- [x] Run `uv run pytest tests/unit/test_session.py tests/unit/test_storage.py -q`; expect missing interfaces/test failures.
- [x] Implement explicit cookie-only HAR import with safe malformed-capture errors and trusted domains from the prototype. Preserve secure/HttpOnly/path/expiry metadata on round trips; reject duplicate ambiguous cookie identities. Use same-directory private temporary files and atomic replacement, with no cookie values in errors. Document importing an existing cookie file by copying it into the configured location while stopped. Worker and import acquire the same lock.
- [x] Run the two test files and migrated cookie tests; expect pass. Add session capture/import instructions based on official Safari documentation and actual verified capture behavior; flag unverified UI variations rather than guessing.
- [x] Checkpoint files and results.

### Task 3: Migrate guarded rewards and produce typed countdown observations

**Files:** Create rewards.py and tests/unit/test_rewards.py, tests/browser/test_rewards.py, tests/fixtures/rewards.html; migrate daily_rewards.py and both existing reward test files; start docs/troubleshooting.md.

**Interfaces:** `parse_countdown(text: str, label: str) -> timedelta | None`; `DailyRewards(page: Page, settings: Settings, stop_requested: Callable[[], bool], emit: Callable[[RewardResult], None])`; `DailyRewards.run(*, login_only: bool = False) -> RunResult`. Preserve individual validators with typed signatures. Emit each completed result immediately for partial-state recovery.

- [x] Port the existing safety and popup regression tests first. Add assertions: `Resets in 11h 10m` yields 670 minutes, `Available in 0m` yields zero, malformed/ambiguous text yields None; countdown observation time anchors next availability. Assert a successful gift response with NextFreeGift and no availability flag plus new UI timer confirms a claim. Assert a response predating the current click cannot confirm it, and a submitted claim without confirmation becomes uncertain with exactly one mutation attempt.
- [x] Run `uv run pytest tests/unit/test_rewards.py -q`; expect failures for new interfaces/observations. Browser fixture tests must intercept all traffic, rejecting unhandled external URLs; no account cookies.
- [x] Move the existing workflow with minimal interaction changes: exact DisplayName + visible name, scoped nav, zero-cost/free availability checks, explicit known popup close controls, dismissal animation waits, popup-aware readiness, DOM scrolling, and timer scoping. Inject settings/time/stop checks instead of global printing/defaults. Use action-specific Playwright response expectations for POSTs; keep GET observations scoped to the current page/run. Preserve result ordering, stop later actions on unsafe failure, and emit completed results before rethrowing/classifying failures.
- [x] Run unit tests and `uv run playwright install chromium` followed by `uv run pytest tests/browser -q`; expect all migrated fixtures passing without skip. If browser launch is blocked by this environment, record the precise limitation and arrange CI/container execution; do not count skips as browser verification. Document popup/uncertain-claim troubleshooting.
- [x] Checkpoint files and results. Remove superseded top-level reward implementation/tests only after migrated coverage passes; compatibility wrapper is handled in Task 6.

### Task 4: Implement pure scheduling and restart-safe state

**Files:** Create scheduler.py, state.py, tests/unit/test_scheduler.py, tests/unit/test_state.py; expand docs/configuration.md.

**Interfaces:** `ScheduleState` with schema version, fingerprint, per-reward failure streaks, last results, next_check_at, and deadline provenance; `plan_next_run(settings: Settings, previous: ScheduleState | None, result: RunResult) -> ScheduleState`; `load_state(path: Path, settings: Settings, now: datetime) -> ScheduleState | None`; `save_state(path: Path, state: ScheduleState) -> None`; `initial_deadline(settings: Settings, state: ScheduleState | None, now: datetime) -> datetime`.

- [x] Write fake-time tests with `t` in UTC: wheel next availability t+11h10m and gift t+11h11m produce wake t+11h11m30s; missing gift timer gives t+15m when earlier; first error t+5m, consecutive errors 10m/20m/40m/60m, then remain capped; a valid availability observation resets the reward's streak. Assert fixed `1h` waits from completion, errors can retry sooner, authentication block gives t+1h, missing partial results retry after error delay, and disabled rewards never affect the minimum.
- [x] Add persistence tests: matching future state honored, overdue runs now, fingerprint change or malformed/unsupported JSON rebuilds immediately; invalid dates/naive timestamps/nonfinite numeric values rejected; absurd retry/fallback deadlines rejected while a valid provenance-backed multi-day countdown survives restart. Model wall-clock jumps and ensure calculation never yields a busy loop (minimum one second).
- [x] Run both files; expect failures. Implement pure functions and schema validation with typed standard-library JSON conversion. Fingerprint exactly username, enabled rewards, mode and scheduling durations; never persist credentials or raw API data. Use Task 2 atomic storage. Do not trust a provenance flag alone: verify stored deadline is consistent with its observation/countdown/buffer or configured retry calculation.
- [x] Run `uv run pytest tests/unit/test_scheduler.py tests/unit/test_state.py -q`; expect pass. Write configuration reference with defaults, precedence, duration examples, restart effects, and relative paths, matching the actual Settings fields.
- [x] Checkpoint files and results.

### Task 5: Own browser runs, signals, retries, and worker health

**Files:** Create browser.py, supervisor.py, worker.py, diagnostics.py, tests/unit/test_browser.py, test_supervisor.py, test_worker.py, test_diagnostics.py under tests/unit/.

**Interfaces:** `run_browser(settings: Settings, stop_event: Event, emit: Callable[[RewardResult], None], *, login_only: bool = False) -> RunResult`; `supervised_run(settings: Settings, stop_event: Event, *, login_only: bool = False, auth_only: bool = False) -> RunResult`; `run_worker(settings: Settings, stop_event: Event, *, once: bool = False, login_only: bool = False) -> int`; `health_status(settings: Settings, now: datetime) -> bool`. Event is multiprocessing's context Event; obtain it from a spawn context. Structured, safe child messages carry partial results/auth state/stage, never cookies. Health JSON is separate from scheduling state.

- [x] Write failing tests with fake browser/clock/child targets: browser closes on success/failure; authenticated cookies save before close; rejected identity never saves; cleanup error preserves primary failure; browser absent during wait. Parent receives partial wheel result before child crash, marks interrupted active mutation uncertain, does not launch another child until old one is reaped, and retries through fresh availability only. Use a harmless blocking synthetic child for actual RUN_TIMEOUT and SIGTERM tests—no browser/network required.
- [x] Add tests for a 23-hour saved wait: heartbeat remains current, SIGTERM wakes promptly, system clock forward/backward is re-evaluated within 60 seconds, and stop prevents new claim actions. Assert health is false on auth block/stale heartbeat/dead worker and true during healthy sleep; starting a second worker fails lock acquisition. Set heartbeat period 30s and stale threshold 120s; validate PID/instance identity to avoid stale-file health on startup.
- [x] Run these test files; expect failures. Implement parent-owned lifetime account lock, spawn child/IPC, supervisor deadlines and cooperative stop. At deadline request stop; after cleanup budget terminate and reap child/process group, including driver descendants, before another run. On SIGTERM total shutdown is at most SHUTDOWN_TIMEOUT; RUN_TIMEOUT may be followed by the configured cleanup budget. Child checks stop before actions; uncertain submitted mutations never loop locally. Read session each child run, not once per worker lifetime.
- [x] Implement safe UTC stream logging; optional RotatingFileHandler (5 MiB, 3 backups); screenshot files mode0600/directories0700; bounded retention of only app-named regular files without following symlinks. Avoid arbitrary exception text/Playwright call logs in normal output: safe stage/type/reason and sanitized frame locations suffice. Include tests with synthetic token/cookie strings asserting absence in logs, state, and errors.
- [x] Run the four test files and `uv run mypy src/monopolygo_rewards`; expect passes. Record process cleanup behavior on macOS and Linux separately, with any platform restriction explicit.
- [x] Checkpoint files and results.

### Task 6: Deliver the CLI, migration path, and local operating guides

**Files:** Create cli.py, __main__.py, tests/unit/test_cli.py; modify script.py, SESSION_PROBE.md; create README.md, docs/setup.md, docs/running.md and complete docs/session.md/troubleshooting.md.

**Interfaces:** `main(argv: Sequence[str] | None = None) -> int`; console `monopolygo-rewards = monopolygo_rewards.cli:main`. Commands: default worker; `--once`; `--login-only`; `import-session --har PATH`; `healthcheck`. Shared options `--env-file`, `--state`, `--username`; runtime `--headless`/`--headed`; `--keep-open` only with headed once/login-only. The prototype wrapper adds --once by default to preserve old behavior; legacy --har prints an explicit import migration instruction rather than silently importing.

- [x] Write failing subprocess/CLI-boundary tests: both entry points show help without session/username requirements; import needs no username/network; missing session returns2; wrong username returns2; successful skip/claim returns0; workflow/uncertain returns1; normal modes never prompt; keep-open invalid combinations fail before browser launch. Assert auth-only recovery checks permit a full reward check only after identity is verified (a fresh run is acceptable).
- [x] Run `uv run pytest tests/unit/test_cli.py -q`; expect failures. Wire config, session/import locks, healthcheck and worker. Validate command-specific requirements; distinguish scheduled auth recovery from startup configuration failure. Add clear credential-free migration messages and mark session_probe as an optional legacy diagnostic, not a runtime dependency.
- [x] Run the CLI tests, `uv run monopolygo-rewards --help`, `uv run python -m monopolygo_rewards --help`, `uv run python script.py --help`, and `uv build`; expect passes and installable wheel/sdist. Smoke install the wheel in a temporary environment and run --help outside the checkout to detect src-path assumptions.
- [x] Write copyable local setup/run examples using the implemented CLI, links to official prerequisite installation docs, and the distinction between macOS/iOS session capture and local/Linux worker runtime. Make login-only the first live command users run; do not execute it against this account during implementation.
- [x] Checkpoint files and results.

### Task 7: Build the nonroot Docker runtime and offline CI

**Files:** Create Dockerfile, .dockerignore, compose.yml, .github/workflows/ci.yml, scripts/container_smoke.py, tests/container/test_runtime.py; extend docs/setup.md, docs/running.md, docs/development.md.

**Interfaces:** image entrypoint `monopolygo-rewards`; Compose service `rewards`, container directories `/app/data`, `/app/artifacts`, optional `/app/logs`; health command `monopolygo-rewards healthcheck`. Configured volume paths must match environment paths. Container UID/GID defaults10001; document ownership preparation; do not chmod777 or run the app as root.

- [x] Write failing smoke assertions: built image has nonzero UID, wheel import/--help succeeds, no workspace HAR/.env/cookies in layers/context, supplied mounted synthetic session/state writable, Chromium loads a local fixture and performs no external calls, one-shot offline run exits0, SIGTERM during a long synthetic wait exits within budget and leaves no running child. Add Compose validation asserting an example user timeout/interval survives env loading; app default paths map to mounted container directories.
- [x] Run smoke commands before image build; expect image-not-found/fixture failure, not contact with live services. Implement a pinned supported multi-stage Debian/Ubuntu Python image from Task1, frozen uv production install, Playwright Chromium + OS libraries at build time, browser binaries readable by nonroot, explicit COPY allowlist and exec entrypoint. .dockerignore must exclude secrets even when names differ from prototype defaults.
- [x] Configure Compose: env_file .env; explicit container path mapping with documented host-side directory controls; init true, shm_size 1gb, restart unless-stopped, healthcheck, stop grace > configured shutdown timeout. Derive grace through a separately documented `CONTAINER_STOP_GRACE_PERIOD` (default30s) with validation guidance; do not blindly add `s` to compound app duration strings. Pass user app settings without hardcoding their defaults over env_file.
- [x] Run `docker compose --env-file <synthetic-env> config --quiet`, `docker build -t monopolygo-rewards:dev .`, `uv run python scripts/container_smoke.py --image monopolygo-rewards:dev`; expect validated Compose and passing smoke assertions. Docker unavailable/blocked is a reported unverified gate, not a pass. Verify amd64 and arm64 builds before claiming both supported.
- [x] Configure CI checkout/setup-uv/locked sync, Ruff format/check, mypy, pytest unit + offline browser fixtures, image build and container smoke. Browser fixtures must fail CI if Chromium is unavailable, rather than silently skip. Add OCI labels/version input; no registry push until a target and credentials are separately configured. Document build/run/update/logs/health/volume setup and the browser-version update procedure.
- [x] Checkpoint files and results.

### Task 8: Reconcile documentation and complete regression verification

**Files:** Finish README.md, .env.example, all six user/developer guides; create tests/unit/test_documentation.py; finalize progress document; remove obsolete duplicate test/implementation files only where replaced.

**Interfaces:** README links to setup/session/running/configuration/development/troubleshooting. Configuration table and .env.example expose all Settings fields plus clearly separated Compose-only settings; no undocumented effective defaults.

- [x] Write a focused failing documentation consistency test: every supported env name exists in the reference/example; internal file links resolve; required CLI examples use supported options. Do not add tests asserting arbitrary prose or formatting. Verify documented shell commands manually against --help and offline setup where possible.
- [x] Run the documentation test; expect any missing references to fail. Complete the guides with prerequisites and official acquisition links, fresh-checkout setup, synthetic/offline development, live/manual acceptance separation, compatibility wrapper migration, session replacement, health/auth troubleshooting, and known unverified platform steps. No real URLs containing tokens or screenshots of credentials in docs.
- [x] Run `uv sync --frozen`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src/monopolygo_rewards`, and `uv run pytest -q`; expect passes. Configure default local pytest for unit tests; explicitly run `uv run pytest tests/browser -q` for mandatory offline browser fixtures so opt-in no longer silently hides coverage. Repeat container smoke only if changes since Task7 affect its behavior.
- [x] Check artifact/source/build-context exclusions, package contents, lock/state behavior, README quickstart and all documented CLI help. Record actual passing counts, blocked commands and remaining live acceptance checks, especially a real gift claim. Do not represent session renewal or live reward claiming as verified by fixtures.
- [x] Final checkpoint and review: report deliverables, tested behavior, environment limitations and starting documentation links. Do not merge, publish, create Git history, or enable a live scheduled worker automatically.

## Plan Self-Review

- Coverage: Tasks1/6 handle package and commands; Task2 sessions/locks; Task3 guarded claims/countdowns; Tasks4/5 scheduling/lifetime/health; Task7 Docker/CI; documentation grows with each deliverable and is reconciled in Task8.
- Interface consistency: all consumers use Settings, RewardResult, RunResult and ScheduleState defined here; only child IPC carries partial safe outcomes, never session data.
- Review Focus: each of the five risks has explicit assertions in its owning task.
- Keep changes incremental; preserve prototype behavior until its replacement tests run. No unnecessary API/database, notifications, multi-account work, or secret migration beyond explicit import.
- Native execution completed with an independent review and one regression-tested fix pass. See 2026-11-09-python-project-progress.md for verification, implementation rulings, and the deferred minor health-check limitation.
