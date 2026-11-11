# MONOPOLY GO Rewards

A Python/Playwright worker for one account. It verifies your exact username, checks the free daily wheel and daily shop gift, claims available free rewards, and skips rewards on cooldown. It closes Chromium between checks and manages its own countdown-based schedule. Optional Apprise notifications report scheduled-worker startup and failures, with successful checks configurable too. A blank notification URL disables delivery.

Start with [setup](docs/setup.md), then [running locally or in Docker](docs/running.md). See [session capture/import](docs/session.md), [configuration](docs/configuration.md), [local development](docs/development.md), and [troubleshooting](docs/troubleshooting.md).

Session reuse has worked for over 24 hours. Automatic renewal of an expired session has not been established; import a fresh capture if authentication fails. No paid rewards or loyalty-point purchases are supported. Session files and HAR captures are credentials.

The package lives in `src/monopolygo_rewards/`; tests use synthetic offline pages under `tests/`. See [CI/CD setup](docs/ci-cd.md) for tests, linting, Docker/PyPI publishing and Trivy scanning. Design and implementation records live under `docs/superpowers/`.
