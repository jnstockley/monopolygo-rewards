# Python project, Docker, and scheduling design

Status: implemented. Subsequent user requests added TZ display support and optional Apprise notifications, superseding the original notification non-goal below. Current settings and behavior are documented in docs/configuration.md; verification and decisions are recorded in the implementation progress document.

## Intent and scope

Turn the working MONOPOLY GO prototype into a maintainable Python application for one account. Run locally or continuously in Docker, verify the configured username before any reward action, claim only the free daily wheel and free shop gift, and skip unavailable rewards. The user wants the application to manage its schedule, including an automatic mode based on the website's countdowns. User-facing settings belong in `.env` and can also be supplied as environment variables.

The reference is `jnstockley/api`, inspected in the sibling `../api` checkout. Follow its conventions where appropriate: uv, pyproject.toml, a lockfile, src layout, pytest, Ruff, standard logging, Docker, Compose, and GitHub Actions. An HTTP API, database, and web UI are outside this phase.

Preserve the tested popup handling, navigation scopes, exact DisplayName verification, zero-cost checks, and independent API/UI confirmation of claims. Do not replace working site interactions just to reorganize the code. The user has verified cooldown runs and wheel claiming; the adjusted gift claim confirmation still needs a live check when available.

## Approaches

1. **Single worker with a small scheduling loop — selected by the user.** One sequential workflow and one interruptible wait; few dependencies and direct control over countdown scheduling and retries.
2. **Scheduler library.** Useful for many jobs or calendar expressions, but adds machinery for this single-account sequential workflow. Not selected.

External-only scheduling was considered earlier. The user explicitly requires internal scheduling. Keep a one-shot command for diagnostics and optional external scheduling.

## Project structure and dependencies

Use an installable `src/monopolygo_rewards/` package with a console entry point `monopolygo-rewards` and `python -m monopolygo_rewards`. Organize by responsibility:

- `config.py`: typed settings, dotenv loading, validation, and duration parsing.
- `models.py`: typed reward results, account outcomes, and persisted scheduler state.
- `session.py`: session import, validation, and atomic cookie persistence.
- `browser.py`: Playwright lifecycle and bounded cleanup.
- `rewards.py`: identity verification and existing guarded browser workflow; split further only where it improves clarity.
- `scheduler.py`: pure next-run calculation plus the worker loop.
- `cli.py`, `__main__.py`: commands, logging setup, signals, and exit codes.

Use standard-library dataclasses, enums, pathlib, logging, and argparse rather than an application framework. Runtime dependencies are Playwright and python-dotenv; development uses pytest, Ruff, and a type checker. Use uv for dependency management with a committed lockfile. Precise dependency and Python versions are implementation choices, verified against available Playwright wheels and the Docker base; do not copy the reference's Python version without checking compatibility. Local and container Python minor versions must agree.

Adopt type annotations throughout the new package. Keep selectors and API paths as implementation details, not user configuration. Migrate tests to `tests/`; retain meaningful regression fixtures. Provide a temporary `script.py` compatibility entry point for existing invocations, accepting current useful flags. Replace runtime HAR fallback with explicit import, with a clear migration message and documentation.

## Commands and configuration

Default command: start the continuously scheduled worker. `--once` checks all enabled rewards once and exits. `--login-only` verifies identity without claims and exits. `import-session --har PATH` explicitly imports the existing captured authentication cookies into the configured session file; it does not send requests. `--keep-open` is an explicit interactive debugging option, valid only with one-shot/login-only and a headed browser. It is never required for normal shutdown.

Configuration precedence: explicit CLI overrides for supported flags, process environment, `.env`, defaults. Read `.env` from the current working directory; allow `--env-file PATH`. Validate configuration before launching Chromium. Log the names of invalid settings without logging their secret values. No implicit shell execution or expansion of setting contents.

Proposed settings (defaults are design choices, except the username supplied by the user):

| Setting | Default | Meaning |
|---|---|---|
| `EXPECTED_USERNAME` | required; example `WonderfulFinch83` | Exact API DisplayName and visible account name |
| `CHECK_INTERVAL` | `auto` | `auto` or a positive duration such as `1h` |
| `FALLBACK_INTERVAL` | `15m` | Retry when a normal result lacks a usable countdown |
| `RESET_BUFFER` | `90s` | Added to countdown estimates to handle display rounding |
| `ERROR_RETRY_INTERVAL` | `5m` | Initial retry after transient/uncertain failure |
| `ERROR_RETRY_MAX_INTERVAL` | `1h` | Maximum exponential error retry delay |
| `AUTH_RETRY_INTERVAL` | `1h` | Read-only identity retry after authentication failure or mismatch |
| `WHEEL_ENABLED` | `true` | Enable free wheel checks |
| `GIFT_ENABLED` | `true` | Enable free shop gift checks |
| `HEADLESS` | `true` | Chromium mode; headed is for local debugging |
| `ACTION_TIMEOUT` | `15s` | Playwright action timeout |
| `NAVIGATION_TIMEOUT` | `45s` | Page navigation timeout |
| `READINESS_TIMEOUT` | `45s` | API/UI/popup readiness timeout |
| `RUN_TIMEOUT` | `5m` | Upper bound on a complete browser run |
| `SHUTDOWN_TIMEOUT` | `20s` | Cleanup budget before forced worker termination |
| `DATA_DIR` | `./data` | Persistent session and scheduling state directory |
| `SESSION_FILE` | `session.cookies` | Absolute path or path relative to DATA_DIR |
| `ARTIFACT_DIR` | `./artifacts` | Private failure screenshots |
| `ARTIFACTS_ENABLED` | `true` | Save inspection screenshots on failure |
| `ARTIFACT_RETENTION_DAYS` | `7` | Bound diagnostic artifact retention |
| `LOG_LEVEL` | `INFO` | Standard logging level |
| `LOG_DIR` | unset | Optional rotating file logs; stdout always enabled |

Support combined duration units (`1h 30m`, `90s`) consistently. Reject zero/negative scheduling intervals, invalid booleans, inconsistent retry bounds, and a configuration with both rewards disabled in worker/once mode. Allow zero reset buffer. Internal minimum wait is one second to prevent a busy loop. Do not expose secrets, API signatures, browser internals, arbitrary URLs, or selectors as general settings. Document every supported setting in `.env.example` and README. Runtime configuration changes require a process restart.

## Session lifecycle

Keep the current Mozilla cookie file compatible, including existing `.monopoly-session.cookies` imports. Production runs require an explicitly prepared session file; they do not need the HAR or captured JavaScript. Preserve permitted authentication cookie domains, paths, security flags, and expiry information. Missing/expired credentials prevent reward actions.

Create a fresh browser/context each run and load session state from disk each time so an externally replaced session is picked up without a worker restart. Save the current permitted authentication cookies atomically after an authenticated run and before closing the context, preserving any legitimate updates made by the site. Files are owner-only where supported. A failed login must not overwrite the last usable session. Import uses the same lock as the worker; instruct users to stop the worker while importing.

Session reuse has been observed for over 24 hours. No renewal endpoint has been proven. Persisting updated cookies does not establish that expired sessions can be renewed. If the site rejects a session, the user must capture/import a new session; never manufacture fast-login tokens or repeatedly redeem captured links.

## Results and countdowns

Return typed per-reward results: reward identifier, status (`claimed`, `skipped`, `failed`, or `uncertain`), safe reason, observation time in UTC, optional displayed countdown, and optional next-available UTC timestamp. Authentication failures are account-level outcomes. Preserve completed results if a later step fails.

Parse only the scoped reward's recognized countdown format into a duration, recording UTC at the moment that text is read. Support displayed days/hours/minutes/seconds and reject malformed or ambiguous text. Zero means due, not unknown. Do not assume a fixed 23-hour or 24-hour reset. After a confirmed claim, read the new countdown to schedule the next check. API success plus required UI confirmation remain the definition of a confirmed claim.

An uncertain claim means the click may have reached the server but completion was not confirmed. Never retry the claim directly. The next run re-verifies identity and reads fresh page/API availability before deciding whether a new free claim is appropriate. Do not retry mutations automatically through generic retry wrappers. Correlate claim responses to the current action so cached responses cannot confirm a later action.

## Scheduler behavior

One run at a time, wheel then gift when enabled, using one fresh browser. Each scheduled run checks all enabled rewards, including those with later stored deadlines; current page state always overrides stored estimates. Close the browser before sleeping. A single process lock on DATA_DIR prevents concurrent workers/one-shot runs from sharing the session or claiming concurrently.

In `auto` mode, calculate a candidate per enabled reward:

- Normal result with a countdown: observation time + displayed duration + RESET_BUFFER.
- Normal result without a usable countdown: completion time + FALLBACK_INTERVAL.
- Failed/uncertain result: completion time + error retry delay for that reward.
- An enabled reward not reached because the run stopped: completion time + error retry delay.

Wake at the earliest candidate, clamped to at least one second after the present. A countdown failure for one reward must not postpone another known earlier deadline. Backoff is per reward, doubling on consecutive errors and capped at ERROR_RETRY_MAX_INTERVAL; a successful availability observation clears that reward's failure streak. In fixed mode, normal checks run CHECK_INTERVAL after completion, but transient failures can trigger an earlier retry; choose the earlier of the normal interval and error delay. Authentication failures/mismatches override reward scheduling with AUTH_RETRY_INTERVAL and permit only identity verification until the expected account is confirmed again.

Persist schema version, effective schedule fingerprint (username, enabled rewards, mode, durations), last outcomes, failure streaks, and next check UTC atomically after each run. No cookies or profile payloads belong in this file. On first start, missing/invalid state, or a changed fingerprint, check immediately. On restart with matching valid state, honor the saved future wake time; overdue state runs immediately. A one-shot run always checks immediately and updates scheduling state. Bound unreasonable persisted deadlines using the largest configured scheduling interval, while accepting legitimate long countdowns observed by the workflow; store enough provenance to distinguish them. Ignore corrupt or unsupported state with a warning and safely rebuild it.

Use UTC wall time for persisted deadlines and monotonic time for bounded actions/backoff waits. Re-evaluate UTC periodically during long sleeps (at most 60 seconds) so clock changes do not strand the worker. SIGINT/SIGTERM interrupt sleep immediately. During a browser run, stop starting new reward actions, allow an already-submitted claim a bounded confirmation/cleanup opportunity, persist known results, and exit within the shutdown budget. Enforce RUN_TIMEOUT through a supervisor boundary that can terminate a blocked browser/driver without allowing overlapping runs; the implementation plan will choose the exact process arrangement. Never keep the browser open while the worker is idle.

## Failures, logging, and exit behavior

Use focused error types for configuration, session/authentication, transient browser/network failure, unsupported UI, and uncertain claims. A browser crash or unknown popup stops that run, captures permitted diagnostics, then uses bounded retry scheduling. A username mismatch performs no claims and remains in identity-only retry mode. On recovery, recompute scheduling from fresh observations.

Log UTC time, severity, workflow stage, reward status/reason, retry delay, and next check time through stdlib logging. Routine cooldown skips are successful outcomes. Never log cookies, raw HAR data, profile bodies, request headers, response bodies, or token-bearing URLs. Diagnostic screenshots may contain account details; keep them private and out of source/images. Delete only application-created artifacts older than retention, without following symlinks. File logs, when enabled, rotate with bounded retention.

One-shot exit codes: 0 for all enabled rewards claimed/skipped successfully; 1 for workflow/uncertain failures; 2 for configuration/session/authentication failures. Scheduled mode continues through recoverable failures and exits nonzero only on startup/fatal errors. SIGTERM exits cleanly. Cleanup exceptions must not hide the original error. Provide a local `healthcheck` command based on worker state/heartbeat, with no browser launch or network requests. Health should remain good during normal long waits, and report unhealthy for stale/dead workers or authentication-blocked state. Health status does not itself restart the container.

## Container and repository delivery

Deliver Dockerfile, `.dockerignore`, `compose.yml`, development instructions, `.env.example`, README, pyproject.toml, uv.lock, tests, and CI. Use a pinned supported Debian/Ubuntu-based Python runtime with the matching Playwright Chromium and OS dependencies installed at build time. Use a build stage and frozen production dependencies. Verify browser/package compatibility instead of copying the API service's browser-free runtime. Run as a nonroot user with a writable mounted data/artifact directory; document host ownership setup. No download/install step at container startup.

Compose loads `.env`, passes validated settings, mounts data and artifacts, sets `init: true`, adequate Chromium shared memory, a stop grace period longer than SHUTDOWN_TIMEOUT, healthcheck, and `restart: unless-stopped`. No host port or persistent database is required. Default to headless. Entrypoint uses exec semantics for reliable signal delivery. Explain which Compose values require recreation. Exclude `.env`, all HARs, cookies, runtime state, artifacts, `.venv`, editor metadata, and caches from build context and source control. Use explicit COPY instructions rather than copying private workspace contents indiscriminately.

CI installs locked dependencies, runs Ruff/type checks/unit tests plus offline browser fixtures, builds the image, and runs offline container smoke checks. No CI uses real account credentials or claims live rewards. Define an image workflow consistent with the reference's OCI metadata and release tagging, but do not enable registry publishing without a real repository/registry target and credentials. Local Docker deliverables do not depend on registry publishing. Verify architectures before advertising support.

## Documentation

Documentation is a deliverable of this phase, maintained alongside the implementation. Provide a concise README that introduces the project and links to focused guides under `docs/`. A new user should be able to get from a fresh checkout to a verified authenticated run without relying on this conversation or the design documents.

- **Project overview (`README.md`):** purpose, supported free rewards, single-account scope, how identity checks and scheduling work, current limitations, repository layout, and links to setup, configuration, operation, and development guides. Clearly distinguish session reuse from proven session renewal.
- **Requirements and setup (`docs/setup.md`):** required account access, a successful authenticated session capture, supported operating systems/architectures, the selected Python version and uv for local execution, and Docker with Compose for container execution. Explain which prerequisites each route needs and link to official installation instructions. Include browser/system dependency installation for local Playwright and explain that the Docker image includes these dependencies. Start with a checklist, then provide ordered setup commands, `.env.example` copying, directory preparation, and a login-only verification step before enabling claims.
- **Obtaining and importing a session (`docs/session.md`):** explain how to enable iOS Safari Web Inspector, connect and trust the iOS device on a Mac, inspect the website opened from the game, preserve the successful navigation's network log, and export the HAR. Document verified troubleshooting for unavailable export controls and missing capture data without inventing browser capabilities. Explain the import command, compatibility with the prototype cookie file, expected file locations/permissions, and how to replace an expired session while the worker is stopped. Treat HARs and cookies as credentials; use placeholder paths and never include real account tokens. Document the macOS/iOS capture route separately from the platforms that can run the worker.
- **Running and operating (`docs/running.md`):** copyable commands for local scheduled mode, one-shot checks, login-only checks, and optional headed inspection; Docker build and Compose start, stop, logs, health, and updates. Explain mounted data/artifact ownership, restart behavior, graceful shutdown, auto versus fixed schedules, retry behavior, account mismatch, and exit codes. Include migration from `python script.py` and `.monopoly-session.cookies`, and explain how configuration changes take effect.
- **Configuration reference (`docs/configuration.md`):** document every supported environment setting with its type, default, units, allowed values, effect, and whether it is required. Explain precedence, relative path resolution, duration syntax, `.env` location, CLI overrides, and validation errors. Include minimal local and Docker examples, plus `auto` and fixed-interval examples. Keep this reference and `.env.example` consistent with actual settings.
- **Local development (`docs/development.md`):** explain getting the source, installing the selected Python and uv, syncing locked development dependencies, installing Chromium, running the package from source, and using a headed browser. Provide exact commands for formatting/linting, type checking, unit tests, offline Playwright fixtures, and container smoke tests. Explain architecture and module boundaries, fake-clock scheduler testing, adding regression fixtures for site changes, dependency/browser version updates, and the checks CI runs. Default development tests must not require real credentials or submit live claims; describe any manual live acceptance check separately.
- **Troubleshooting (`docs/troubleshooting.md`):** cover missing/expired cookies, username mismatch, popups, missing timers, uncertain claims, browser installation/launch failures, container permissions, an existing worker lock, and apparently idle workers waiting for their next check. Explain where to find safe logs/screenshots, how to enable useful diagnostics, and how to report a failure without sharing credentials.

Document only commands and behavior that the implementation actually supports. Validate CLI examples against `--help`, run the offline quickstart and container examples where the environment permits, check internal links and configuration names, and explicitly identify any instructions that could not be verified. The final handoff should identify the starting page for users and the development guide for contributors. Design and implementation-plan documents are supplemental engineering records, not substitutes for user documentation.

## Verification and acceptance

- Regression coverage retains identity mismatch, zero-cost enforcement, popup races/animations, countdown skips, successful confirmations, uncertain claims, and cleanup error handling.
- Pure clock-controlled scheduler tests cover countdown parsing, separate deadlines, fixed mode, missing timers, backoff, partial results, auth recovery, restarts, corrupted state, configuration changes, and signal interruption.
- Configuration/session tests cover precedence, duration validation, expired cookies, import compatibility, atomic writes, and exclusion of credentials from diagnostic output.
- Offline Playwright fixtures exercise the packaged entry point, including both available rewards and repeated popup dismissal. No live account needed.
- Container smoke checks verify package import, CLI, nonroot writable volumes, Chromium launch against local fixtures, one-shot exit, and prompt shutdown during a long wait.
- Documentation checks confirm that setup and operation examples match the implemented CLI, configuration reference matches `.env.example`, and a fresh user can follow the documented offline/local and Docker paths without conversation context.
- User acceptance: actual account verifies; unavailable rewards skip; available free rewards claim once; new countdowns select the next run; browser closes between checks; restart preserves the schedule; replacing session recovers authentication. A real gift claim remains an explicitly identified live acceptance check, not a prerequisite for offline CI.

## Builder decisions and limitations

The module names, standard-library settings model, configuration defaults above, same-run checks of both rewards, backward-compatible wrapper, and identity-only hourly recovery are proposals made by the assistant. Dependency versions, packaging backend, type checker, exact supervisor mechanics, fixture details, and build-stage layout are left to implementation with compatibility verification. Do not add multiple accounts, notifications, a server, purchase actions, a database, or automatic expired-session renewal in this phase.

The workspace has no `.git` directory. Save the design and implementation plan here; do not initialize a repository, create a remote, publish images, or claim a commit was made without a separate instruction.
