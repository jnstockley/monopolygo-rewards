import signal
import subprocess
import sys


def test_signal_interrupts_parent_wait_without_locking():
    code = "from monopolygo_rewards.cli import StopRequest; import signal; s=StopRequest(); signal.signal(signal.SIGTERM, lambda *_: s.set()); print('ready', flush=True); s.wait(60); print(s.is_set(), flush=True)"
    process = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "ready"
        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=2)
        assert process.returncode == 0 and output.strip() == "True"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
