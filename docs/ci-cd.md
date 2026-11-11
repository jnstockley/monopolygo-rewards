# CI/CD

Adapted from the local `jnstockley/api` checkout's `ci-cd.yml` and `security.yml`. The workflows retain its Docker Hub/GHCR destinations, Infisical OIDC credentials, PyPI trusted publishing, main development builds, release builds and weekly Trivy scan. The template sync workflow is intentionally excluded: it merges a different starter repository into a `dev` branch.

## Checks and publishing

`.github/workflows/ci-cd.yml` runs on pull requests, pushes to `main`, published releases (including prereleases), and manual dispatches. It runs Ruff formatting/lint, mypy, YAML lint, unit tests and offline Chromium/notification tests. It builds a wheel and sdist, checks the installed wheel CLI, builds the Docker image and runs the existing offline container smoke script. Python 3.15.2 comes from `.python-version`; uv is pinned to 0.13.7. No live account session or reward requests are needed.

Both publishing jobs require all checks and the reusable Trivy workflow to pass. Pull requests and manual CI dispatches never publish or fetch publishing credentials. Main pushes publish development packages to production PyPI, matching the API repository's convention.

| Event | PyPI version | Docker tags |
| --- | --- | --- |
| Push to `main` | UTC `YYYYMMDDHHMMSS.devN`, where N is the run attempt | `dev`, same development version |
| Published prerelease `v0.2.0rc1` | `0.2.0rc1` | `testing`, `0.2.0rc1`, `v0.2.0rc1` |
| Published stable release `v0.2.0` | `0.2.0` | `latest`, `0.2.0`, `v0.2.0` |

Use valid Python package versions as release tags, optionally prefixed with `v`. Mark prereleases appropriately in GitHub. Publishing a previously used PyPI version fails; rerunning an already published stable release is not an overwrite operation. Both deployment jobs use the same version; `uv version --no-sync` refreshes root lock metadata so Docker's frozen installation installs that version. The PyPI job downloads the distributions already verified by the build job.

Images target `linux/amd64` and `linux/arm64`, under `<DOCKER_USERNAME>/<repository-name>` and `ghcr.io/<repository-owner>/<repository-name>`, normalized to lowercase. GHCR uses the repository owner rather than the triggering actor. The existing package name remains `monopolygo-rewards`, independently of the GitHub repository name. OCI labels come from Docker metadata and the Dockerfile. The two publish jobs run independently after checks; one destination can succeed while another fails.

## Required account setup

This source directory currently has no Git metadata or configured remote. Add these files to the intended GitHub repository before configuring the following settings there.

1. Enable GitHub Actions and create `pypi` and `docker` environments. If environment deployment branch/tag restrictions are enabled, allow `main` and your release tags.
2. On PyPI, create a pending trusted publisher for `monopolygo-rewards` (or add a publisher to that project if you own it). Set the actual GitHub owner and repository, workflow filename **`ci-cd.yml`**, and environment **`pypi`**. No PyPI API token is used. See [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).
3. In the GitHub `docker` environment, set variable `INFISICAL_IDENTITY_ID`. Configure that identity's GitHub OIDC trust to permit this repository and environment. At `https://secrets.jstockley.com`, use an Infisical project slug matching the actual GitHub repository name and environment slug `prod`. Provide `DOCKER_USERNAME` and `DOCKER_PASSWORD` (a Docker Hub token with push permission). These follow the API workflow's existing secret names. DHI credentials are unnecessary for this project's public Python and uv base images.
4. Ensure the Docker Hub account can push to the image repository. Allow `GITHUB_TOKEN` package writes to the GHCR package, especially if a package with that name already exists.
5. Enable GitHub code scanning/SARIF support for the repository to display Trivy findings in Security. Private repositories need an eligible GitHub security plan. Same-repository runs upload SARIF to Security; fork PRs and release runs preserve reports as artifacts without that upload. Release uploads are excluded because their tag reference is not a code-scanning branch reference.

These account settings cannot be created or verified from this directory. No publication has been triggered locally.

## Security scanning

`.github/workflows/security.yml` is called by CI and also runs every Wednesday at 20:22 UTC and on manual dispatch. Standalone runs rebuild the checked-out source instead of requiring a previously published `latest` tag or registry credentials. Trivy 0.76.2 scans source/locked dependencies and the local Linux image for vulnerabilities, secrets and misconfiguration. The image includes the installed Python dependencies and browser/system packages. This follows the [Trivy action's supported scan modes](https://github.com/aquasecurity/trivy-action).

Scans fail on HIGH/CRITICAL findings; vulnerabilities without fixes are ignored, matching the API workflow. Both SARIF reports are preserved as the `trivy-reports` artifact even when findings fail a scan. Scan failures block both publishing jobs. Keep Trivy and its action up to date along with base images and dependencies.

Image scanning and offline container smoke checks run on the Ubuntu runner's native `amd64` image. The publishing job rebuilds both architectures; an `arm64` execution or architecture-specific vulnerability check is not covered by these native checks. Scheduled scans rebuild current source/base tags and do not audit an immutable digest from a prior publication.
