# Local development

Use Python3.15 and uv0.13.7, matching `.python-version`, `pyproject.toml`, `uv.lock`, CI and the Docker base. Get uv from its [official installation guide](https://docs.astral.sh/uv/getting-started/installation/). The workspace currently has no Git repository/remote; obtain the source directory directly until one is assigned.

```sh
uv python install 3.15
uv sync --frozen
uv run playwright install chromium
# Linux CI/development: uv run playwright install --with-deps chromium
cp .env.example .env
```

Do not overwrite an existing `.env`. Use synthetic fixtures for automated work; real HARs/cookies are private and never needed by CI.

## Checks

```sh
uv run ruff format .
uv run ruff check .
uv run mypy src/monopolygo_rewards
uv run pytest -q
uv run pytest tests/browser -q
uv build
```

Notification integration tests send only to a temporary loopback HTTP receiver; the offline CLI runner explicitly disables configured notifications. Never test with real provider URLs.

The default pytest suite runs unit tests, including a real spawned child timeout. Browser tests are a separate explicit command and fail if Chromium cannot launch; they do not silently skip. Both reward states and popup cases use intercepted synthetic HTML/API responses, and unknown URLs are aborted. To exercise the installed CLI plus worker and supervisor against offline pages:

```sh
uv run python tests/browser/run_offline.py --once
OFFLINE_AVAILABLE=1 uv run python tests/browser/run_offline.py --once
```

For real local inspection only, first import a session and verify identity, then use `uv run monopolygo-rewards --once --headed --keep-open`. This can claim live free rewards and is not a substitute for offline tests. Normal development should not run a live scheduled worker.

## Architecture

`config.py` validates typed settings. `session.py` imports and persists trusted cookies through private atomic files; `storage.py` owns the Unix lock. `rewards.py` retains guarded page interactions and emits typed results from `models.py`. `scheduler.py` is pure UTC deadline/backoff logic; `state.py` validates persisted JSON. `browser.py` owns a single context and cookie updates. `supervisor.py` spawns a browser process group and bounds its lifetime. `worker.py` owns the account lock, next-run loop, state, heartbeat and shutdown. `cli.py` connects these pieces; `diagnostics.py` limits logs/artifacts.

Keep scheduling tests deterministic: supply literal UTC times and hand-calculated deadlines, rather than sleeping hours or computing expected values with the production helper. Test process deadlines with short synthetic child targets. Add a minimal regression page or API payload for site changes and watch the test fail before changing interactions. Preserve exact username, free-cost, mutation-once and popup-dismissing safeguards.

## Container checks

```sh
docker build -t monopolygo-rewards:dev .
uv run python scripts/container_smoke.py --image monopolygo-rewards:dev
```

The smoke script mounts only tests, uses disposable synthetic data and disables container networking. It checks package help, Compose env propagation, UID, private volume writes, Chromium fixtures, both free claims against fixtures, and SIGTERM during scheduled sleep. No production session is mounted. Its world-writable temporary test directory is not an example for real credential storage.

CI repeats locked sync, formatting/lint, mypy, unit and browser tests, package build, image build and smoke checks. Trivy scans source, locked dependencies and a locally built image before publishing. Main pushes and published releases publish packages and images after all checks succeed; pull requests and manual CI runs only check the build. See [CI/CD setup](ci-cd.md) for credentials, trusted publishing, tags and scan behavior. OCI version metadata is supplied through Docker's VERSION build argument.

## Updating dependencies

Change versions deliberately in pyproject.toml, regenerate `uv.lock` with `uv lock`, sync with `uv sync --frozen`, reinstall browsers and run the checks. Playwright browser binaries must match the installed package; rebuild the image after a Playwright update rather than retaining old binaries. See [Playwright's Docker instructions](https://playwright.dev/python/docs/docker). Match Python minor across package constraints, `.python-version`, Docker and CI; validate actual wheels before upgrading. Docker bases and uv image tags are pinned; periodically review and rebuild for fixes.

## Manual acceptance

After offline checks, the account owner may test login, a cooldown skip, and a genuinely available free reward. Confirm exactly one claim response and the new countdown, then verify browser closure, next deadline and restart persistence. Real session lifetime/renewal cannot be proven by offline fixtures. The original wheel claim has been observed live; the revised gift confirmation still requires live acceptance. Document outcomes without capturing token values in reports.
