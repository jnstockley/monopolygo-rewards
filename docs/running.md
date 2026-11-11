# Running and operating

Complete [setup](setup.md), configure `.env`, and verify identity first.

## Commands

```sh
uv run monopolygo-rewards --login-only
uv run monopolygo-rewards --once
uv run monopolygo-rewards
uv run python -m monopolygo_rewards --once
```

The default worker runs continuously. Every run verifies identity, visits Benefits then Shop for enabled rewards, skips cooldowns and claims only explicitly available free items. Auto mode uses the earliest displayed reset plus `RESET_BUFFER`, with `FALLBACK_INTERVAL` when no usable timer is available. It does not assume a 23-hour or 24-hour reset. `CHECK_INTERVAL=1h` selects checks one hour after the prior run finishes; failures can cause an earlier retry.

Chromium is closed before each wait. Scheduling state survives restarts. Matching valid state honors its saved future deadline; overdue, invalid or configuration-changed state checks immediately. Each run checks both enabled rewards. Partial results survive later failures. Consecutive failures back off per reward from 5m to a maximum1h by default; a successful observation resets that streak.

A possible-but-unconfirmed claim is marked uncertain and is never clicked again immediately. The next scheduled browser run checks fresh page/API availability first. Rejected identity prevents all claims and switches to identity-only retries. Fixing credentials requires a new import if the session cannot be reused; the worker has no proven renewal mechanism.

For local inspection:

```sh
uv run monopolygo-rewards --once --headed --keep-open
```

This waits for Enter after checking; normal modes never prompt. RUN_TIMEOUT still bounds inspection, so increase it temporarily if needed. Ctrl-C stops local work. SIGTERM interrupts scheduled sleep immediately and requests bounded browser cleanup. Do not run a second worker or one-shot check on the same data directory while the first holds its lock.

## Docker

```sh
docker compose build
docker compose run --rm rewards --login-only
docker compose run --rm rewards --once
docker compose up -d
docker compose logs -f --tail=100 rewards
docker compose ps
docker compose exec rewards monopolygo-rewards healthcheck
docker compose stop rewards
```

The image uses UID/GID10001, headless Chromium, no exposed ports and no database. Data, screenshots and optional file logs are mounted separately. See [setup](setup.md) for directory ownership. Docker healthchecks make no network requests and launch no browser; long scheduled waits are healthy, rejected identity is unhealthy. Health status alone does not trigger a restart; `restart: unless-stopped` restarts an exited worker until you stop it.

After updating source or dependencies:

```sh
docker compose stop rewards
docker compose build
docker compose up -d --force-recreate
```

For `.env` changes, recreate the container with `docker compose up -d --force-recreate`; restarting an existing container does not reload its environment. Set `CONTAINER_STOP_GRACE_PERIOD` longer than `SHUTDOWN_TIMEOUT`, including cleanup overhead. Defaults are30s and20s. Compound application durations and Compose duration syntax are separate; configure both explicitly when changing shutdown budgets.

## Logs, state and exit codes

Logs go to stdout with timestamps in `TZ` (default UTC) and stage/status/retry information. Set `TZ=America/Chicago` for local times with daylight saving and an explicit UTC offset; saved scheduling/health timestamps remain UTC. Set `LOG_DIR` for bounded rotating logs (5MiB per file, three backups); use `/app/logs` in Docker. Failure screenshots are private files in ARTIFACT_DIR and removed after retention. Keep them out of issue reports until reviewed for account details.

`data/schedule.json` contains safe scheduling observations and retry streaks; `data/health.json` contains heartbeat/status/PID; `data/worker.lock` is the advisory lock file. Never delete a lock file to bypass a running worker. A clean stop releases the OS lock even though its file remains. To reset a schedule, stop the worker and remove only schedule.json; the next worker start checks immediately.

One-shot exit codes:0 claimed/skipped successfully;1 workflow or uncertain failure;2 configuration/session/authentication error. Scheduled operation continues through recoverable failures, logs next check time, and exits nonzero on startup/fatal errors. A graceful stop exits0.

Health-check limitation: heartbeat age and a live PID are checked, but a unique process-instance identity is not yet stored. After an abrupt exit and PID reuse, a stale heartbeat could briefly appear healthy (up to120s). This does not bypass identity verification or permit reward actions. Keep each account in a single DATA_DIR; separate data directories do not share a lock even if they reference the same cookie file.

Optional success/failure notifications use [Apprise settings](configuration.md#notifications). Leave APPRISE_URL empty to disable them; select APPRISE_NOTIFY_ON=error (default) or all. Scheduled starts also notify by default; APPRISE_NOTIFY_STARTUP=false disables startup notices. Delivery failures are logged without changing reward outcomes.
