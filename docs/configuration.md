# Configuration

Copy `.env.example` to `.env`, then change EXPECTED_USERNAME. Supported precedence is explicit CLI override, process environment, literal dotenv setting, default. Dotenv values do not expand shell commands or `${VARIABLE}` references. Environment settings are read once; restart/recreate after changes. The default file is `.env` in the working directory; select another with `--env-file PATH`.

Durations are nonnegative integer units: `90s`, `15m`, `1h 30m`, `1d2h`; duplicate units, negatives, fractions and unknown units are rejected. Intervals/timeouts must be positive. Only RESET_BUFFER accepts zero. Booleans accept true/false, yes/no,1/0 (case insensitive). Relative paths use the startup working directory, except SESSION_FILE relative to DATA_DIR; `~` is expanded.

| Setting | Type/default | Effect |
|---|---|---|
| EXPECTED_USERNAME | string, required for runs | Exact API DisplayName and visible name; example WonderfulFinch83 |
| CHECK_INTERVAL | `auto` or duration; auto | Earliest reset or fixed interval after run completion |
| FALLBACK_INTERVAL | duration;15m | Normal result with no usable countdown |
| RESET_BUFFER | duration;90s | Added to reset estimates;0s allowed |
| ERROR_RETRY_INTERVAL | duration;5m | Initial error/uncertain retry |
| ERROR_RETRY_MAX_INTERVAL | duration;1h | Capped doubling retry delay; cannot be below initial retry |
| AUTH_RETRY_INTERVAL | duration;1h | Identity-only recovery checks |
| WHEEL_ENABLED | boolean;true | Enable free wheel checks |
| GIFT_ENABLED | boolean;true | Enable free shop gift checks |
| HEADLESS | boolean;true | Hide Chromium; false requires a local display |
| ACTION_TIMEOUT | duration;15s | Default Playwright action wait |
| NAVIGATION_TIMEOUT | duration;45s | Page navigation wait |
| READINESS_TIMEOUT | duration;45s | Upper bound for individual readiness/availability polling |
| RUN_TIMEOUT | duration;5m | Browser child run deadline, then bounded cleanup |
| SHUTDOWN_TIMEOUT | duration;20s | Cooperative cleanup budget before force termination |
| DATA_DIR | path;./data | Account lock, schedule, health and default cookie directory |
| SESSION_FILE | path;session.cookies | Relative to DATA_DIR unless absolute |
| ARTIFACT_DIR | path;./artifacts | Failure screenshots |
| ARTIFACTS_ENABLED | boolean;true | Capture screenshots on failures |
| ARTIFACT_RETENTION_DAYS | positive integer;7 | Remove app-created old screenshots only |
| TZ | IANA timezone;UTC | Log and next-check display, e.g. America/Chicago; daylight saving applied automatically, saved state remains UTC |
| APPRISE_URL | optional Apprise service URL;empty | Empty/whitespace disables all notification delivery. Treat a configured URL as a credential |
| APPRISE_NOTIFY_ON | error/all;error | Errors only, or both errors and successful checks (including cooldown skips) |
| APPRISE_NOTIFY_STARTUP | boolean;true | Send a scheduled-worker startup notice, independently of error/all mode |
| APPRISE_TIMEOUT | positive duration;10s | Maximum notification delivery wait; shutdown interrupts it |
| LOG_LEVEL | DEBUG/INFO/WARNING/ERROR/CRITICAL;INFO | Stdout and optional file logging level |
| LOG_DIR | optional path;empty | Enable rotating file logs |

Both rewards disabled is invalid for scheduled/one-shot runs, but allowed for login verification. Import and health commands do not need EXPECTED_USERNAME. Selectors, API paths and paid-action safeguards are implementation details and are intentionally not configurable.

CLI overrides: `--state PATH` sets SESSION_FILE; `--username NAME` sets EXPECTED_USERNAME; `--headed`/`--headless` overrides HEADLESS. `--keep-open` requires a headed one-shot or login-only run. `--once` checks immediately, ignoring a future saved deadline. The package without these run-mode flags schedules continuously.

## Examples

Minimal local `.env`:

```dotenv
EXPECTED_USERNAME=WonderfulFinch83
CHECK_INTERVAL=auto
```

Fixed hourly checks:

```dotenv
EXPECTED_USERNAME=WonderfulFinch83
CHECK_INTERVAL=1h
ERROR_RETRY_INTERVAL=5m
ERROR_RETRY_MAX_INTERVAL=1h
```

## Compose-only settings

| Setting | Default | Meaning |
|---|---|---|
| HOST_DATA_DIR | ./data | Host directory mounted at /app/data |
| HOST_ARTIFACT_DIR | ./artifacts | Host directory mounted at /app/artifacts |
| HOST_LOG_DIR | ./logs | Host directory mounted at /app/logs |
| CONTAINER_STOP_GRACE_PERIOD |30s | Docker stop grace; keep longer than SHUTDOWN_TIMEOUT |

Compose always sets container DATA_DIR=/app/data and ARTIFACT_DIR=/app/artifacts; use HOST_* to change host paths. Other application settings come from `.env`. Keep SESSION_FILE relative or set a container path. To enable file logging in Docker, set LOG_DIR=/app/logs. HEADLESS=false is for local development; the image does not provide a desktop/VNC server.

Compose interpolates its YAML separately from application dotenv loading; avoid `${...}` values. Container environment changes need recreation, not just restart. Shell-provided Compose interpolation values override `.env` for HOST_* and stop grace; application values can be overridden with `docker compose run -e NAME=value` for a single command.

## Notifications

Apprise notifications are optional and disabled until APPRISE_URL is set. Use a service URL from the [Apprise documentation](https://github.com/caronc/apprise#supported-notifications), such as a provider URL or `apprise://host/config-key` for an Apprise API server. A plain HTTP URL for a server's web interface is not an Apprise service URL. No additional server is required for direct providers.

```dotenv
APPRISE_URL=
APPRISE_NOTIFY_ON=error
APPRISE_NOTIFY_STARTUP=true
APPRISE_TIMEOUT=10s
```

Set APPRISE_NOTIFY_ON=all for both errors and successes. Success means every enabled reward was claimed or skipped normally; a cooldown skip is successful. Failed, uncertain, incomplete, unauthenticated, and wrong-account runs are errors. One summary is attempted per completed reward run, including retries, with account name, reward results and next check in TZ. Login-only reports its own outcome; session import and healthcheck do not notify. Runtime/startup errors after configuration is loaded also notify; settings that cannot be parsed are logged only. When a URL is configured, the scheduled worker attempts one startup notice after acquiring its account lock and initializing state/health, before waiting for its next check. This includes the account and next check time; it does not confirm authentication. Startup notices are independent of error/all mode; set APPRISE_NOTIFY_STARTUP=false to disable them. One-shot and login-only commands do not emit startup notices. No notifications are sent merely for sleeping or intentionally stopping the worker.

Delivery is best-effort, bounded by APPRISE_TIMEOUT, and has no automatic notification resend. A provider failure does not change reward results, exit status or scheduling and never retries a claim. Notification URLs/plugin exception details are excluded from logs and saved scheduling state; notifications contain no cookies, raw API bodies or screenshots. Treat the configured destination as an authorized recipient of the account name and reward summary. Recreate Docker after changing notification settings.
