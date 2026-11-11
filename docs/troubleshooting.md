# Troubleshooting

Start with the workflow stage and next-check log, displayed in the configured `TZ` (UTC by default). Do not paste HARs, cookie values, request headers, raw API bodies or token-bearing URLs into reports.

| Symptom | Checks and recovery |
|---|---|
| Required cookies missing/expired | Check SESSION_FILE path and permissions; import a successful authenticated capture. A logged-out desktop HAR is insufficient. [Session guide](session.md) |
| Profile username mismatch | Compare EXPECTED_USERNAME with the exact visible DisplayName, including case. Do not change the guard merely to bypass a different account. No rewards are claimed while identity is rejected |
| Worker seems idle | Read `Next check:`; auto mode sleeps until earliest reset+buffer. Browser intentionally closes while waiting. Stop the worker, then use --once to check immediately |
| Authentication remains blocked | Import a fresh session while stopped, then verify --login-only. Reusing cookies does not guarantee expired-session renewal |
| Popup or wheel/shop readiness timeout | Inspect the private screenshot and logged stage. Known dismissal controls are handled, unknown blocking dialogs stop the run. Add an offline regression before changing selectors; never choose arbitrary CTA/logout controls |
| Gift/wheel marked uncertain | The server may already have acted. Do not immediately replay the click; let a fresh run check availability and countdown. Missing confirmation is not proof the claim failed |
| Timer missing or invalid | Normal successful observations use FALLBACK_INTERVAL; an actual failed workflow uses error retry. Do not assume every reset is exactly23h/24h |
| Browser executable missing | Run `uv run playwright install chromium`; on Linux add --with-deps. Rebuild Docker after dependency changes |
| Browser/driver launch denied | Verify the host permits process launch. IDE/sandbox restrictions are separate from application failures. Run offline fixtures in a normal local terminal or container to isolate the environment |
| Container cannot read/write session/data | Container user is UID/GID10001. Check mounted paths and ownership per [setup](setup.md); do not chmod777 real credentials |
| Another worker holds the lock | Stop the other worker/container. A remaining worker.lock filename alone is normal; the OS descriptor lock releases on exit. Do not remove the file to bypass a running owner |
| Container unhealthy during rejected identity | Expected: the process stays running but health reports blocked. Fix the session/username. Docker health alone does not restart it |
| Notifications not arriving | Check APPRISE_URL is a supported Apprise service URL, APPRISE_NOTIFY_ON and provider credentials. Error-only mode suppresses successful check summaries; startup notices have their own APPRISE_NOTIFY_STARTUP switch. No notification is emitted merely while waiting. Delivery failures/timeouts are logged without the URL; rebuild/recreate after setting changes |
| `.env` edits have no effect | Local process needs restart; Compose container needs recreation. Check explicit CLI/process-environment overrides and container paths |

Logs always go to stdout. LOG_LEVEL controls verbosity; LOG_DIR enables bounded file logs. ARTIFACTS_ENABLED controls private screenshots; ARTIFACT_DIR sets their location and ARTIFACT_RETENTION_DAYS bounds retention. Review screenshots for account information before sharing. Unexpected driver exception text is omitted because it can contain credentials; report the stage, exception type, safe message, version and offline reproduction instead.

