"""Terminate whole native client trees on disposable test hosts."""
import os
import signal
import subprocess


def stop_client(process):
    if os.name == 'nt':
        if process.poll() is None:
            subprocess.run(['taskkill.exe', '/T', '/F', '/PID', str(process.pid)],
                           capture_output=True, timeout=15)
        return
    try:
        # POSIX clients are launched in a private session so their helpers and
        # telemetry children cannot outlive a disposable home.
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        if process.poll() is None:
            process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        if process.poll() is None:
            process.kill()
    if process.poll() is None:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
