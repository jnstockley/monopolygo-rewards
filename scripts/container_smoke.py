"""Offline image smoke checks. Synthetic credentials; no live account requests."""

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="monopolygo-rewards:dev")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    def run(*command: str) -> str:
        result = subprocess.run(command, check=True, text=True, capture_output=True, timeout=90)
        return result.stdout + result.stderr

    assert "--once" in run("docker", "run", "--rm", "--network", "none", args.image, "--help")
    assert run("docker", "run", "--rm", "--entrypoint", "id", args.image, "-u").strip() != "0"
    with tempfile.TemporaryDirectory() as name:
        data = Path(name)
        # Disposable synthetic fixture directory: explicitly writable to UID10001.
        data.chmod(0o777)
        code = "from pathlib import Path; from monopolygo_rewards.storage import atomic_write_json; atomic_write_json(Path('/app/data/test.json'), {'offline': True}); assert not list(Path('/app').glob('*.har')); assert not Path('/app/.env').exists()"
        run(
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{data}:/app/data",
            "--entrypoint",
            "python",
            args.image,
            "-c",
            code,
        )
        assert (data / "test.json").stat().st_mode & 0o777 == 0o600
        shutil.copy(root / "compose.yml", data / "compose.yml")
        (data / ".env").write_text(
            "EXPECTED_USERNAME=synthetic\nCHECK_INTERVAL=7h\nACTION_TIMEOUT=9s\n"
        )
        config = json.loads(
            run("docker", "compose", "-f", str(data / "compose.yml"), "config", "--format", "json")
        )
        env = config["services"]["rewards"]["environment"]
        assert env["CHECK_INTERVAL"] == "7h" and env["ACTION_TIMEOUT"] == "9s"
        assert env["DATA_DIR"] == "/app/data"

    tests = f"{root / 'tests'}:/qa/tests:ro"
    print(
        run(
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--shm-size",
            "1g",
            "-v",
            tests,
            "--entrypoint",
            "python",
            args.image,
            "-m",
            "unittest",
            "discover",
            "-s",
            "/qa/tests/browser",
        )
    )
    output = run(
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--shm-size",
        "1g",
        "-e",
        "OFFLINE_AVAILABLE=1",
        "-v",
        tests,
        "--entrypoint",
        "python",
        args.image,
        "/qa/tests/browser/run_offline.py",
        "--once",
    )
    assert "wheel: claimed" in output and "gift: claimed" in output
    container = run(
        "docker",
        "run",
        "-d",
        "--network",
        "none",
        "--shm-size",
        "1g",
        "-v",
        tests,
        "--entrypoint",
        "python",
        args.image,
        "/qa/tests/browser/run_offline.py",
    ).strip()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            logs = run("docker", "logs", container)
            if "gift: skipped" in logs and logs.count("Next check:") >= 2:
                break
            time.sleep(0.2)
        else:
            raise AssertionError("Offline worker did not reach its scheduled sleep")
        started = time.monotonic()
        run("docker", "stop", "--time", "25", container)
        elapsed = time.monotonic() - started
        print("Stopped container in", elapsed, "seconds")
        print(run("docker", "logs", container))
        print(run("docker", "inspect", "--format", "{{.State.ExitCode}}", container))
        assert elapsed < 22
        assert run("docker", "inspect", "--format", "{{.State.ExitCode}}", container).strip() == "0"
    finally:
        run("docker", "rm", "-f", container)
    print(
        "Offline image checks passed: CLI, Compose configuration, nonroot writes, Chromium fixtures, both claims, scheduled sleep and SIGTERM."
    )


if __name__ == "__main__":
    main()
