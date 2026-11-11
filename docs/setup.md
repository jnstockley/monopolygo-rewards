# Setup

Choose local Python execution or Docker. Both routes require an account you can sign into, its exact visible username, and either the prototype cookie file or a successful iOS session HAR. Importing a session does not establish that it is still valid; verify it before enabling reward checks.

## Prerequisites and where to get them

| Requirement | Local | Docker | Installation/source |
|---|---|---|---|
| Project source | Required | Required to build | Copy this project or clone its eventual repository; no remote is configured yet |
| Python 3.15 | Required | Included in image | [Python downloads](https://www.python.org/downloads/) or `uv python install 3.15` |
| uv 0.13.7 | Required | Included in build stage | [Official uv installation](https://docs.astral.sh/uv/getting-started/installation/) |
| Chromium and system libraries | Required | Included in image | `uv run playwright install chromium`; Linux: add `--with-deps` |
| Docker Engine/Desktop and Compose v2 | Optional | Required | [Docker installation](https://docs.docker.com/engine/install/) and [Compose installation](https://docs.docker.com/compose/install/) |
| Authenticated session | Required | Required | [Capture/import guide](session.md) |
| Mac + iOS device, cable, Safari, game access | For a new iOS capture | For a new iOS capture | Device's own Safari Web Inspector; not required on the worker host after importing |

Runtime targets are macOS and Linux (Unix file locks and process groups). Native Windows is not supported; use Linux containers. Local macOS arm64 and Linux container verification results are recorded in the [implementation ledger](superpowers/plans/2026-11-09-python-project-progress.md). Do not infer support for other CPU architectures without running the smoke checks there.

## Local quickstart

From the project root:

```sh
uv python install 3.15
uv sync --frozen
uv run playwright install chromium
cp .env.example .env
mkdir -p data artifacts
chmod 700 data artifacts
```

On Linux, install browser OS dependencies with `uv run playwright install --with-deps chromium` (this may request administrator rights). Python patch versions can receive updates within the supported 3.15 minor; `.python-version` pins the build-tested version.

Edit `.env`, especially `EXPECTED_USERNAME`. Prepare the session using one of these alternatives:

```sh
# Import a successful captured session; no request is sent.
uv run monopolygo-rewards import-session --har /path/to/successful-session.har
```

Or copy the existing prototype cookies:

```sh
cp .monopoly-session.cookies data/session.cookies
chmod 600 data/session.cookies
```

Then verify without claims:

```sh
uv run monopolygo-rewards --login-only --headed
```

Only after the expected username verifies, run one check with `uv run monopolygo-rewards --once` or start the scheduled worker with `uv run monopolygo-rewards`. See [running](running.md).

## Docker quickstart

The host does not need Python or uv when using Docker, provided you already have a compatible cookie file. To import a HAR entirely through Docker, see [session import](session.md).

```sh
cp .env.example .env
mkdir -p data artifacts logs
# Copy your existing compatible session.cookies into data/ before starting.
docker compose build
```

Set `EXPECTED_USERNAME` in `.env`. Container user UID/GID is 10001. On Linux, give that user ownership of runtime directories and the cookie file before running; use administrator privileges if required:

```sh
sudo chown -R 10001:10001 data artifacts logs
sudo chmod 700 data artifacts logs
sudo chmod 600 data/session.cookies
```

On Docker Desktop/macOS, bind mount permission behavior varies; verify a one-shot/login-only container can read and write the mounted directory. Do not make real session directories world writable.

```sh
docker compose run --rm rewards --login-only
docker compose run --rm rewards --once
docker compose up -d
```

Do not leave a local worker running against the same data directory. See [configuration](configuration.md) for custom paths and [troubleshooting](troubleshooting.md) for permissions.
